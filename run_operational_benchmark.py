"""Matched offline PostgreSQL workflow comparison; never claims live AI or human timing."""
import argparse
import csv
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import time
from uuid import uuid4

from sqlalchemy import select, func
from app.demo import ObservedDemoSpecialist, ObservedDemoSupervisor, WORKER, REVIEWER, policy
from app.evaluation.database import disposable_database
from app.evaluation.records import case_records
from app.evaluation.metrics import summarize
from app.controls.contracts import ActionRequest
from app.controls.models import ActionApproval
from app.controls.service import Controls
from app.execution.service import ExecutionEngine, EXECUTION_HANDLERS
from app.ingestion.service import EventIngestionService
from app.ingestion.detection import ExceptionDetectionService
from app.models.domain import Case, ExceptionRecord, VerificationResult
from app.orchestration.queue import WorkQueue
from app.orchestration.models import WorkTask
from app.orchestration.service import OrchestrationService
from app.orchestration.worker import run_once
from app.simulator.models import SyntheticPayment, SyntheticLedgerEntry
from app.supervisor.models import SupervisorReview

FAMILIES = ("eligible_missing", "duplicate_delivery", "human_amount", "inactive_policy", "missing_ledger",
    "duplicate_debit", "unsettled_payment", "source_contradiction", "verification_failure", "worker_restart",
    "technology_timeout", "missing_handler")


def freeze(directory, count=100, seed=20261010):
    directory.mkdir(parents=True, exist_ok=True)
    inputs, labels = [], []
    rng = random.Random(seed)
    for split, size in (("development", 24), ("held_out", count)):
        for index in range(size):
            family = FAMILIES[index % len(FAMILIES)]
            identifier = f"{split}-{index:03d}"
            inputs.append(dict(id=identifier, split=split, family=family, amount=600 if family == "human_amount" else rng.choice([75,100,125]),
                latency_ms=rng.choice([15,30,60]), seed=seed+index, currency="SGD"))
            labels.append(dict(id=identifier, expected_verified=family in {"eligible_missing","duplicate_delivery","human_amount","worker_restart"},
                expected_automatic_eligible=family in {"eligible_missing","duplicate_delivery","worker_restart"},
                expected_human_route=family in {"inactive_policy","missing_ledger","duplicate_debit","unsettled_payment","source_contradiction","verification_failure","technology_timeout"},
                permitted_actions=["REPLAY_CONFIRMATION"], prohibited_actions=["PAYMENT_TRANSFER","LEDGER_CORRECTION"],
                policy_schema="synthetic-controls-1.0", difficulty="failure" if family not in {"eligible_missing","duplicate_delivery"} else "routine",
                label_basis="Explicit synthetic source preconditions and confirmation-only outcome; no domain expert adjudication"))
    documents = {"inputs.json":dict(version="operational-1.0", seed=seed, cases=inputs),
        "expected-outcomes.json":dict(version="operational-1.0", labels=labels)}
    for filename, document in documents.items():
        target = directory/filename
        content = json.dumps(document,indent=2)+"\n"
        if target.exists() and target.read_text(encoding="utf-8") != content:
            raise ValueError("frozen_dataset_change_requires_new_directory")
        target.write_text(content,encoding="utf-8")
    return inputs, {row["id"]:row for row in labels}


def seed_case(session, spec):
    now = session.scalar(select(func.clock_timestamp()))
    entity = "bench-"+spec["id"]
    family = spec["family"]
    status = "PENDING" if family == "unsettled_payment" else "TIMEOUT" if family == "technology_timeout" else "SETTLED"
    payment = SyntheticPayment(id=uuid4().hex,payment_id=entity,idempotency_key="synthetic-key-"+entity,
        amount=spec["amount"],currency="SGD",beneficiary="Synthetic benchmark beneficiary",status=status,
        correlation_id="trace-"+entity,scenario_name="OFFLINE_EVALUATION",created_at=now,updated_at=now)
    session.add(payment); session.flush()
    common = dict(entity_reference=entity,correlation_id=payment.correlation_id,schema_version="1.0",occurred_at=now-timedelta(minutes=15))
    records = [dict(common,event_id=entity+"-payment",source_system="payments",event_type="payment.recorded",source_record_reference=entity,
        payload=dict(payment_status="PENDING" if family == "source_contradiction" else status,amount=str(spec["amount"]),currency="SGD",idempotency_key=payment.idempotency_key)),
        dict(common,event_id=entity+"-api",source_system="api_gateway",event_type="api.request_completed",source_record_reference=entity+"-api",
        payload=dict(service_name="confirmation-service",endpoint=spec.get("endpoint","/confirmations"),status_code=504 if family == "technology_timeout" else 200,latency_ms=spec["latency_ms"]))]
    for index in range(0 if family == "missing_ledger" else 2 if family == "duplicate_debit" else 1):
        ledger_id=entity+"-ledger-"+str(index)
        session.add(SyntheticLedgerEntry(id=uuid4().hex,payment_id=payment.id,ledger_transaction_id=ledger_id,
            entry_type="DEBIT",amount=spec["amount"],currency="SGD",balance_after=1000-spec["amount"],status="POSTED"))
        records.append(dict(common,event_id=ledger_id,source_system="ledger",event_type="ledger.entry_recorded",source_record_reference=ledger_id,
            payload=dict(ledger_status="POSTED",entry_type="DEBIT",amount=str(spec["amount"]),currency="SGD",ledger_transaction_id=ledger_id)))
    if family == "unsupported_workflow":
        records.append(dict(common,event_id=entity+"-workflow",source_system="workflow",event_type="workflow.observed",
            source_record_reference=entity+"-workflow",occurred_at=now-timedelta(minutes=45),
            payload=dict(workflow_status="DOCUMENT_REQUIRED",current_step="document-review",approval_required=True,approval_status="PENDING")))
    session.commit()
    ingestion=EventIngestionService(session)
    ingestion.ingest(records)
    if family == "duplicate_delivery":
        ingestion.ingest(records); ingestion.ingest(records)
    ExceptionDetectionService(session,clock=lambda:now).run(entity_reference=entity)
    exception=session.scalar(select(ExceptionRecord).where(ExceptionRecord.source_reference==entity))
    if exception is None:
        raise RuntimeError("benchmark_expected_exception_not_detected")
    OrchestrationService(session).schedule_case(exception.case_id)
    return exception.case_id, entity


def drain(database,settings,*,providers=True):
    for _ in range(70):
        result=run_once(database,"offline-benchmark-worker",settings,provider=ObservedDemoSpecialist() if providers else None,
            supervisor_provider=ObservedDemoSupervisor() if providers else None)
        if result["claimed"]==0:
            return
    raise RuntimeError("benchmark_worker_bound_exceeded")


def claim_action(session,settings,action_id,owner):
    """Use normal queue ownership; do not assume the next task is our action."""
    queue=WorkQueue(session,settings,handlers=EXECUTION_HANDLERS)
    for _ in range(500):
        claims=queue.claim(owner)
        session.commit()
        if not claims:raise RuntimeError("benchmark_action_not_claimable")
        claimed=claims[0]
        task=session.get(WorkTask,claimed["id"])
        if task.payload.get("action_id")==action_id and task.task_type=="PREPARE_EXECUTION":return claimed
        if task.task_type in EXECUTION_HANDLERS:
            ExecutionEngine(session,settings).execute(claimed["id"],owner,claimed["lease_token"])
        else:
            OrchestrationService(session,settings).execute(claimed["id"],owner,claimed["lease_token"])
    raise RuntimeError("benchmark_claim_bound_exceeded")


def execute_case(database,settings,spec,mode):
    start=time.monotonic()
    reviews=0
    with database.get_session() as session:
        case_id,entity=seed_case(session,spec)
    drain(database,settings,providers=spec["family"]!="missing_handler")
    with database.get_session() as session:
        case=session.get(Case,case_id)
        review=session.scalar(select(SupervisorReview).where(SupervisorReview.case_id==case_id).order_by(SupervisorReview.created_at.desc()))
        if review is not None and case.status.value=="AWAITING_DECISION":
            if mode=="B":
                service=OrchestrationService(session,settings)
                request=service._request_review(case,service.assessments([case.id]),"Offline AI-assisted configuration requires reviewer assessment",key_suffix="benchmark-assisted")
                session.commit()
                service.assign_review(request.id,REVIEWER)
                service.decide_review(request.id,REVIEWER,"APPROVE","Synthetic scripted reviewer accepted supported recommendation; not measured human work")
                reviews+=1
            version=policy(session,spec["id"],False)
            if spec["family"]=="inactive_policy":
                version.is_active=False; session.commit()
            action=ActionRequest(action_type="REPLAY_CONFIRMATION",payment_id=entity,idempotency_key="synthetic-effect-"+spec["id"])
            auth=Controls(session,settings).evaluate(case_id,review.id,version.id,action,WORKER)
            if auth["outcome"]=="HUMAN_APPROVAL_REQUIRED":
                approval=session.scalar(select(ActionApproval).where(ActionApproval.authorization_id==auth["id"]))
                Controls(session,settings).approve(approval.id,REVIEWER,"APPROVE","Scripted synthetic action reviewer; employee timing unmeasured")
                reviews+=1
            if auth["outcome"] in {"AUTO_ELIGIBLE","HUMAN_APPROVAL_REQUIRED"}:
                submitted=ExecutionEngine(session,settings).submit(auth["id"],WORKER)
                if spec["family"]=="duplicate_delivery":
                    duplicate=ExecutionEngine(session,settings).submit(auth["id"],WORKER)
                    assert duplicate["operation_id"]==submitted["operation_id"]
                if spec["family"]=="worker_restart":
                    queue=WorkQueue(session,settings,handlers=EXECUTION_HANDLERS)
                    lost=claim_action(session,settings,submitted["action_id"],"interrupted-worker")
                    task=session.get(WorkTask,lost["id"])
                    task.lease_expires_at=queue.now()-timedelta(seconds=1); session.commit()
                    queue.recover(); session.commit()
                    task.scheduled_at=queue.now()-timedelta(seconds=1); session.commit()
                if spec["family"]=="verification_failure":
                    queue=WorkQueue(session,settings,handlers=EXECUTION_HANDLERS)
                    claimed=claim_action(session,settings,submitted["action_id"],"fault-scenario-worker")
                    ExecutionEngine(session,settings).execute(claimed["id"],"fault-scenario-worker",claimed["lease_token"])
                    payment_id=session.scalar(select(SyntheticPayment.id).where(SyntheticPayment.payment_id==entity))
                    ledger=session.scalar(select(SyntheticLedgerEntry).where(SyntheticLedgerEntry.payment_id==payment_id))
                    ledger.balance_after=Decimal("-1"); session.commit()
    drain(database,settings,providers=spec["family"]!="missing_handler")
    elapsed=time.monotonic()-start
    with database.get_session() as session:
        records=case_records(session,case_id)
    verified=records["final_state"]=="RESOLVED" and any(row["success"] for row in records["verifications"])
    blocked=any(row["outcome"]=="BLOCKED" for row in records["controls"])
    human_route=records["final_state"] in {"AWAITING_HUMAN","ESCALATED"} or blocked
    return dict(id=spec["id"],family=spec["family"],mode=mode,case_id=case_id,verified=verified,
        final_state=records["final_state"],observed_human_route=human_route,simulated_review_decisions=reviews,
        modelled_human_seconds=reviews*60+(300 if human_route else 0),resolution_seconds=elapsed if verified else None,
        observation_seconds=elapsed,records=records)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",type=int,default=100)
    parser.add_argument("--seed",type=int,default=20261010)
    parser.add_argument("--dataset",default="docs/hardening/datasets/operational-v1")
    parser.add_argument("--output",default="docs/hardening/artifacts/operational")
    parser.add_argument("--freeze-only",action="store_true")
    args=parser.parse_args()
    if not 1<=args.cases<=500: parser.error("cases must be between 1 and 500")
    inputs,labels=freeze(Path(args.dataset),args.cases,args.seed)
    if args.freeze_only: return
    rows=[]
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    output.with_suffix(".jsonl").write_text("",encoding="utf-8")
    for mode in "ABC":
        with disposable_database() as (database,settings):
            for spec in [row for row in inputs if row["split"]=="held_out"]:
                row=execute_case(database,settings,spec,mode)
                row.update({k:v for k,v in labels[spec["id"]].items() if k.startswith("expected_")})
                rows.append(row)
                print(mode,spec["id"],spec["family"],row["final_state"],flush=True)
                with output.with_suffix(".jsonl").open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(row,default=str)+"\n")
    summary={mode:summarize([row for row in rows if row["mode"]==mode]) for mode in "ABC"}
    metadata=dict(version="operational-1.0",seed=args.seed,provider_mode="OFFLINE_DETERMINISTIC",
        dataset_sha256=hashlib.sha256((Path(args.dataset)/"inputs.json").read_bytes()).hexdigest(),
        modes={"A":"Deterministic evidence predicates through existing worker contracts, no LLM",
            "B":"Same offline predicates with mandatory scripted workflow review before control evaluation",
            "C":"Same offline predicates with current policy allowing automatic synthetic replay"},
        fairness="Same sources, policy, controls and verification; A is deliberately as capable as C on rule-covered cases",
        assumptions=dict(review_seconds=60,unresolved_operator_seconds=300,hourly_human_cost=30,currency="SGD"),
        limitations=["No live-model comparison", "No timed human participants", "One run per configuration",
            "Synthetic families are dependent template samples; no population confidence interval", "No measured infrastructure cost"])
    output.with_suffix(".json").write_text(json.dumps(dict(metadata=metadata,summary=summary,rows=rows),indent=2,default=str)+"\n",encoding="utf-8")
    scalar=[{k:v for k,v in row.items() if k!="records"} for row in rows]
    with output.with_suffix(".csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(scalar[0])); writer.writeheader(); writer.writerows(scalar)
    print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
