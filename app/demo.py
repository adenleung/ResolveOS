"""Reproducible observed synthetic journeys, isolated from development and paid AI."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import secrets
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, func, text

from app.config import get_settings
from app.database import DatabaseManager
from app.models.domain import Case, ExceptionRecord, Policy, PolicyVersion, Evidence, VerificationResult, ActionRecord
from app.simulator.models import SyntheticPayment, SyntheticLedgerEntry, SyntheticConfirmationEvent
from app.ingestion.service import EventIngestionService
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import EventRecord
from app.orchestration.auth import Identity
from app.orchestration.worker import run_once
from app.orchestration.service import OrchestrationService
from app.controls.contracts import ActionRequest
from app.controls.service import Controls
from app.controls.models import ActionApproval, ControlAuthorization
from app.supervisor.models import SupervisorReview
from app.execution.service import ExecutionEngine
from app.investigation.contracts import ModelTurn, ToolCall, Output, SupervisorOutput
from app.memory.service import MemoryService
from app.memory.contracts import MemoryAccess, CandidateRequest, ReviewRequest
from app.reliability.service import ShadowService
from app.reliability.contracts import ShadowRequest
from app.intelligence.contracts import AnalyticsAccess
from app.execution.models import ExecutionOperation

WORKER = Identity("demo-worker", frozenset({"WORKER"}))
REVIEWER = Identity("development-reviewer", frozenset({"OPERATIONS_REVIEWER"}))


class ObservedDemoSpecialist:
    identifier = "offline-observed-demo-specialist:1"

    def turn(self, instructions, messages, tools, max_tokens):
        meta = json.loads(messages[0]["content"])
        role = meta["role"]
        if len(messages) == 1:
            name, arguments = ("get_api_request", {"correlation_id": meta["traces"][0]}) if role == "TECHNOLOGY" else (
                "get_payment" if role == "TRANSACTION" else "get_transaction_state", {"payment_id": meta["entities"][0]})
            return ModelTurn(calls=[ToolCall(name=name, arguments=arguments, call_id="observed-demo-query")])
        evidence = json.loads(messages[-1]["output"])["evidence"]
        field = "status_code" if role == "TECHNOLOGY" else "payment_status"
        matching = [row for row in evidence if field in row["payload"]]
        findings = [dict(claim=f"Observed {field} equals {row['payload'][field]}", evidence_ids=[row["id"]],
            assessment="SUPPORTED", field=field, expected_value=row["payload"][field]) for row in matching]
        return ModelTurn(output=Output(summary="Offline demo inspected current normalized source observations.",
            outcome="COMPLETED" if findings else "NEEDS_ADDITIONAL_EVIDENCE", findings=findings, hypotheses=[],
            missing_evidence=[] if findings else ["No supported source predicate available"], contradictions=[],
            suggested_next_steps=["Independent Supervisor review"], proposed_resolution=None, action_authorization="NOT_EVALUATED"))


class ObservedDemoSupervisor:
    identifier = "offline-observed-demo-supervisor:1"

    def turn(self, instructions, messages, tools, max_tokens):
        assert not tools
        snapshot = json.loads(messages[0]["content"])
        conclusions = [dict(claim=row["claim"], evidence_ids=row["evidence_ids"], assessment="SUPPORTED",
            field=row["field"], expected_value=row["expected_value"]) for row in snapshot["findings"] if row["deterministically_supported"]]
        issues = snapshot["issues"]
        return ModelTurn(output=SupervisorOutput(review_version="1.0", outcome="ESCALATE" if issues else "RECOMMENDATION",
            summary="Current specialist predicates independently cross-checked; confirmation replay is advisory only.",
            supported_conclusions=conclusions, rejected_conclusions=[], unresolved_issues=issues,
            required_additional_checks=[], targeted_specialists=[], proposed_action=None if issues else "REPLAY_CONFIRMATION",
            evidence_ids=sorted({ref for row in conclusions for ref in row["evidence_ids"]}),
            escalation_reasons=issues, action_authorization="NOT_EVALUATED"))


def drain(database, settings):
    for _ in range(60):
        result = run_once(database, "isolated-demo-worker", settings, poll=True,
            provider=ObservedDemoSpecialist(), supervisor_provider=ObservedDemoSupervisor())
        if result["claimed"] == 0:
            return
    raise RuntimeError("demo_work_exceeded_bound")


def seed_source(session, label, contradictory=False):
    now = session.scalar(select(func.clock_timestamp()))
    entity = "demo-payment-" + label
    payment = SyntheticPayment(id=uuid4().hex, payment_id=entity, idempotency_key="demo-source-key-" + label,
        amount=100, currency="SGD", beneficiary="Synthetic demonstration beneficiary", status="FAILED" if contradictory else "SETTLED",
        correlation_id="demo-trace-" + label, scenario_name="ISOLATED_DEMO", created_at=now, updated_at=now)
    session.add(payment); session.flush()
    common = dict(entity_reference=entity, correlation_id=payment.correlation_id, schema_version="1.0", occurred_at=now-timedelta(minutes=15))
    records = [dict(common, event_id="demo-payment-event-"+label, source_system="payments", event_type="payment.recorded",
        source_record_reference=entity, payload={"payment_status": payment.status, "amount": "100", "currency": "SGD", "idempotency_key": payment.idempotency_key}),
        dict(common, event_id="demo-api-event-"+label, source_system="api_gateway", event_type="api.request_completed",
        source_record_reference="demo-api-"+label, payload={"service_name": "confirmation-service", "endpoint": "/confirmations",
            "status_code": 200, "latency_ms": 20})]
    if contradictory:
        session.add(SyntheticConfirmationEvent(id=uuid4().hex, payment_id=payment.id, event_id="demo-existing-confirmation-B",
            status="CONFIRMED", occurred_at=now-timedelta(minutes=14), correlation_id=payment.correlation_id))
        records.append(dict(common, event_id="demo-confirmation-event-B", source_system="confirmations", event_type="payment.confirmed",
            source_record_reference="demo-existing-confirmation-B", payload={"confirmation_status": "CONFIRMED", "is_duplicate": False}))
    else:
        ledger = SyntheticLedgerEntry(id=uuid4().hex, payment_id=payment.id, ledger_transaction_id="demo-ledger-"+label,
            entry_type="DEBIT", amount=100, currency="SGD", balance_after=900, status="POSTED")
        session.add(ledger)
        records.append(dict(common, event_id="demo-ledger-event-"+label, source_system="ledger", event_type="ledger.entry_recorded",
            source_record_reference=ledger.ledger_transaction_id, payload={"ledger_status": "POSTED", "entry_type": "DEBIT", "amount": "100",
                "currency": "SGD", "ledger_transaction_id": ledger.ledger_transaction_id}))
    session.commit()
    ingestion = EventIngestionService(session)
    ingestion.ingest(records)
    ingestion.ingest(records)  # duplicate delivery must not create duplicate effects
    ExceptionDetectionService(session, clock=lambda: now).run(entity_reference=entity)
    exception = session.scalar(select(ExceptionRecord).where(ExceptionRecord.source_reference == entity))
    assert exception is not None
    case = session.get(Case, exception.case_id)
    case.summary = {"A": "Missing confirmation after settled payment and posted ledger", "B": "Payment failed but confirmation reports success: human review required",
        "C": "Previously approved replay blocked by changed policy"}[label]
    session.commit()
    OrchestrationService(session).schedule_case(case.id)
    return case.id, exception.id


def policy(session, label, human):
    now = session.scalar(select(func.clock_timestamp()))
    parent = Policy(id=uuid4().hex, name="isolated-demo-controls-"+label, active_version="1")
    session.add(parent); session.flush()
    row = PolicyVersion(id=uuid4().hex, policy_id=parent.id, version="1", is_active=True, effective_from=now-timedelta(days=1),
        content={"policy_schema": "synthetic-controls-1.0", "action_allowlist": ["REPLAY_CONFIRMATION"], "worker_roles": ["WORKER"],
            "approval_role": "OPERATIONS_REVIEWER", "max_amount": "1000", "currency": "SGD", "max_affected_cases": 10,
            "max_blast_radius": 1, "human_approval_required": human, "automatic_amount_limit": "500", "approval_ttl_seconds": 300,
            "authorization_ttl_seconds": 600, "effective_to": (now+timedelta(days=365)).isoformat(), "compensation": "NONE_CONFIRMATION_ONLY"})
    session.add(row); session.commit()
    return row


def build_journeys(database, settings):
    # Called only inside a verifier-owned disposable database or newly created demo DB.
    with database.get_session() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert re.fullmatch(r"resolveos_(demo|backend_verify)_[0-9a-f]{10}", name)
        assert session.scalar(select(func.count()).select_from(Case)) == 0, "Refusing to reseed populated data"
        cases = {label: seed_source(session, label, label == "B") for label in "ABC"}
    drain(database, settings)
    manifest = {"database": name, "provider": "offline deterministic demo over actual source evidence; no external calls", "journeys": {}}
    for label in "AC":
        case_id, exception_id = cases[label]
        with database.get_session() as session:
            review = session.scalar(select(SupervisorReview).where(SupervisorReview.case_id == case_id).order_by(SupervisorReview.created_at.desc()))
            if review is None: raise RuntimeError("demo_supervisor_not_completed:"+label)
            version = policy(session, label, label == "C")
            action = ActionRequest(action_type="REPLAY_CONFIRMATION", payment_id="demo-payment-"+label, idempotency_key="demo-effect-key-"+label)
            shadow = ShadowService(database, settings).evaluate(case_id, ShadowRequest(supervisor_review_id=review.id,
                policy_version_id=version.id, action=action), AnalyticsAccess(REVIEWER))
            auth = Controls(session, settings).evaluate(case_id, review.id, version.id, action, WORKER)
            if label == "A":
                assert auth["outcome"] == "AUTO_ELIGIBLE"
                preview = ExecutionEngine(session, settings).preview(auth["id"], WORKER)
                submitted = ExecutionEngine(session, settings).submit(auth["id"], WORKER)
                duplicate = ExecutionEngine(session, settings).submit(auth["id"], WORKER)
                assert all(duplicate[key] == submitted[key] for key in ("operation_id", "action_id", "simulation_id"))
                manifest["journeys"][label] = {"case_id": case_id, "exception_id": exception_id, "authorization_id": auth["id"],
                    "shadow_id": shadow.id, "simulation_id": preview["id"], "expected_state": "RESOLVED"}
            else:
                assert auth["outcome"] == "HUMAN_APPROVAL_REQUIRED"
                approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == auth["id"]))
                Controls(session, settings).approve(approval.id, REVIEWER, "APPROVE", "Current evidence reviewed in isolated demonstration")
                version.is_active = False; session.commit()
                try: ExecutionEngine(session, settings).submit(auth["id"], WORKER)
                except ValueError as exc: error_code = str(exc)
                else: raise AssertionError("Unsafe stale-policy action was accepted")
                session.rollback()
                blocked = Controls(session, settings).evaluate(case_id, review.id, version.id, action, WORKER)
                assert blocked["outcome"] == "BLOCKED"
                manifest["journeys"][label] = {"case_id": case_id, "exception_id": exception_id, "stale_authorization_id": auth["id"],
                    "authorization_id": blocked["id"], "shadow_id": shadow.id, "approval_id": approval.id,
                    "blocked_request_error": error_code, "expected_control_outcome": "BLOCKED"}
    drain(database, settings)
    with database.get_session() as session:
        b_case, _ = cases["B"]
        assert session.get(Case, b_case).status.value == "AWAITING_HUMAN"
        manifest["journeys"]["B"] = {"case_id": b_case, "exception_id": cases["B"][1], "expected_state": "AWAITING_HUMAN"}
        a_case = cases["A"][0]
        assert session.get(Case, a_case).status.value == "RESOLVED"
        verification = session.scalar(select(VerificationResult).where(VerificationResult.case_id == a_case))
        assert verification.success and verification.verification_type == "INDEPENDENT_SYNTHETIC_CONFIRMATION"
        assert session.scalar(select(func.count()).select_from(ActionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 2
        assert all(row.amount == 100 and row.balance_after == 900 for row in session.scalars(select(SyntheticLedgerEntry)))
        refs = list(session.scalars(select(Evidence.id).where(Evidence.case_id == a_case)))
        memory = MemoryService(session, settings)
        candidate = memory.candidate(a_case, CandidateRequest(category=session.get(ExceptionRecord, cases["A"][1]).exception_type,
            verification_id=verification.id, summary="Historical demonstration: confirmation replay independently verified; posted monetary ledger unchanged.",
            evidence_ids=refs[:20]), MemoryAccess(WORKER))
        memory.review(candidate["id"], ReviewRequest(operation="SUBMIT", reason="Submit verified demonstration history"), MemoryAccess(REVIEWER))
        memory.review(candidate["id"], ReviewRequest(operation="APPROVE", reason="Approve independently verified historical context"), MemoryAccess(REVIEWER))
        session.commit()
        manifest["journeys"]["A"].update(verification_id=verification.id, memory_version_id=candidate["id"])
        manifest["verified_assertions"] = {"bank_amounts_unchanged": True, "duplicate_deliveries_deduplicated": True,
            "duplicate_execution_single_effect": True, "operational_actions": 1, "independent_successes": 1, "development_untouched": True}
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="Create a new separate PostgreSQL demo database")
    parser.add_argument("--manifest", default="demo-manifest.local.json")
    args = parser.parse_args()
    if not args.create:
        manifest = json.loads(Path(args.manifest).read_text())
        assert re.fullmatch(r"resolveos_demo_[0-9a-f]{10}", manifest["database"])
        admin = create_engine(get_settings().database_url)
        database = DatabaseManager(admin.url.set(database=manifest["database"]))
        verify_journeys(database, manifest)
        print("All three persisted demo journeys verified; no records changed."); return
    settings = get_settings()
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    assert admin.url.database == "resolveos" and admin.url.host in {"localhost", "127.0.0.1"} and admin.url.port == 5433
    name = "resolveos_demo_"+uuid4().hex[:10]
    with admin.connect() as connection: connection.execute(text('CREATE DATABASE "'+name+'"'))
    os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
    command.upgrade(Config("alembic.ini"), "head")
    settings = get_settings()
    settings.investigator_live_enabled = False
    manifest = build_journeys(DatabaseManager(settings.database_url), settings)
    verify_journeys(DatabaseManager(settings.database_url), manifest)
    Path(args.manifest).write_text(json.dumps(manifest, indent=2)+"\n")
    Path("phase15-demo-results.json").write_text(json.dumps(manifest, indent=2)+"\n")
    Path(".env.demo").write_text("DATABASE_URL="+settings.database_url+"\nAPP_ENV=development\nORCHESTRATION_DEV_AUTH_ENABLED=true\n"
        +"ORCHESTRATION_DEV_WORKER_TOKEN="+secrets.token_urlsafe(32)+"\nORCHESTRATION_DEV_REVIEWER_TOKEN="+secrets.token_urlsafe(32)
        +"\nINVESTIGATOR_LIVE_ENABLED=false\nRESOLVEOS_BACKEND_URL=http://127.0.0.1:8000\n")
    print(json.dumps(manifest, indent=2))


def verify_journeys(database, manifest):
    with database.get_session() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        assert session.scalar(text("SELECT current_database()")) == manifest["database"]
        for label, journey in manifest["journeys"].items():
            case = session.get(Case, journey["case_id"])
            if label in "AB": assert case.status.value == journey["expected_state"]
            if label == "A":
                verification = session.get(VerificationResult, journey["verification_id"])
                action = session.get(ActionRecord, verification.action_id)
                operation = session.scalar(select(ExecutionOperation).where(ExecutionOperation.action_id == action.id))
                assert verification.success and verification.verification_type == "INDEPENDENT_SYNTHETIC_CONFIRMATION" and action.status == operation.status == "VERIFIED"
            if label == "C":
                assert session.get(ControlAuthorization, journey["authorization_id"]).outcome == "BLOCKED"
                assert session.scalar(select(func.count()).select_from(ActionRecord).where(ActionRecord.case_id == case.id)) == 0
        assert all(row.amount == 100 and row.balance_after == 900 for row in session.scalars(select(SyntheticLedgerEntry)))
        assert session.scalar(select(func.count()).select_from(ActionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 2


if __name__ == "__main__": main()
