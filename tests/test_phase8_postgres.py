import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select, func

from test_phase6_postgres import postgres_engine, session, source_case, drain
from test_phase7_postgres import FakeModel
from app.config import Settings
from app.database import DatabaseManager
from app.domain.case_service import CaseState
from app.investigation.contracts import HANDLERS, ModelTurn, SupervisorOutput
from app.investigation.service import InvestigationRunner
from app.models.domain import ActionRecord, AuditLog, Case, Evidence, HumanApproval
from app.orchestration.models import TaskConsumer, WorkTask
from app.orchestration.queue import LeaseLost, WorkQueue
from app.orchestration.service import OrchestrationService
from app.orchestration.worker import run_once
from app.supervisor.models import SupervisorReview
from app.supervisor.service import SupervisorRunner, SUPERVISOR_TASK

@pytest.fixture
def settings():
    return Settings(orchestration_lease_seconds=30, investigator_token_budget=50000,
                    orchestration_max_attempts=2, orchestration_backoff_seconds=1)

class FakeSupervisor:
    identifier = "deterministic-supervisor-test:1"
    def __init__(self, outcome="RECOMMENDATION", fabricated=False, error=None, mutate=None):
        self.outcome, self.fabricated, self.error, self.mutate = outcome, fabricated, error, mutate
    def turn(self, instructions, messages, tools, cap):
        assert not tools
        if self.error:
            raise self.error
        data = json.loads(messages[0]["content"])
        finding = data["findings"][0]
        refs = ["nonexistent"] if self.fabricated else finding["evidence_ids"]
        if self.mutate:
            self.mutate()
        output = SupervisorOutput(review_version="1.0", outcome=self.outcome,
            summary="Independent review of observed predicates", supported_conclusions=[
                dict(claim="Observed predicate", evidence_ids=refs, assessment="SUPPORTED",
                    field=finding["field"], expected_value=finding["expected_value"])],
            rejected_conclusions=[], unresolved_issues=[], required_additional_checks=["Check transaction-state discrepancy"] if self.outcome == "REINVESTIGATE" else [],
            targeted_specialists=["TRANSACTION"] if self.outcome == "REINVESTIGATE" else [],
            proposed_action=None, evidence_ids=refs, escalation_reasons=[], action_authorization="NOT_EVALUATED")
        return ModelTurn(output=output, input_tokens=100, output_tokens=100)

def investigated(session, settings):
    case, exception = source_case(session)
    OrchestrationService(session, settings).schedule_case(case.id)
    drain(session, settings)
    database = DatabaseManager(session.get_bind().url)
    tasks = session.execute(select(WorkTask).where(WorkTask.case_id == case.id,
        WorkTask.task_type.in_(HANDLERS)).order_by(WorkTask.id)).scalars().all()
    for task in tasks:
        task.priority = -100
        session.commit()
        role = task.task_type.removeprefix("INVESTIGATE_")
        runner = InvestigationRunner(database, settings, FakeModel(role))
        runner.activate(session)
        claim = WorkQueue(session, settings, handlers=HANDLERS).claim("specialist")[0]
        session.commit()
        assert claim["id"] == task.id
        assert runner.run(task.id, "specialist", claim["lease_token"])["outcome"] == "COMPLETED"
        session.refresh(task)
        task.priority = 2
        session.commit()
    session.refresh(case)
    assert case.status == CaseState.AWAITING_DECISION
    supervisor = session.execute(select(WorkTask).where(WorkTask.case_id == case.id,
        WorkTask.task_type == SUPERVISOR_TASK)).scalar_one()
    return case, supervisor, database, tasks

def claimed_review(session, settings, provider=None):
    case, task, database, work = investigated(session, settings)
    task.priority = -100
    session.commit()
    runner = SupervisorRunner(database, settings, provider or FakeSupervisor())
    runner.activate(session)
    claim = WorkQueue(session, settings, handlers={SUPERVISOR_TASK}).claim("supervisor")[0]
    session.commit()
    assert claim["id"] == task.id
    return case, task, runner, claim, work

def test_supervisor_recommendation_not_authorization(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings)
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "RECOMMENDATION" and result["action_authorization"] == "NOT_EVALUATED"
    session.refresh(case)
    assert case.status == CaseState.AWAITING_DECISION
    assert session.scalar(select(func.count()).select_from(ActionRecord)) == 0
    assert session.scalar(select(func.count()).select_from(HumanApproval)) == 0

def test_supervisor_fabricated_reference_rejected(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings, FakeSupervisor(fabricated=True))
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "FAILED" and result["error_code"] == "supervisor_fabricated_evidence"
    session.refresh(task)
    assert task.status == "DEAD_LETTER"

def test_supervisor_targeted_reinvestigation_preserves_other_work(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings, FakeSupervisor("REINVESTIGATE"))
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "REINVESTIGATE"
    session.refresh(case)
    assert case.status == CaseState.INVESTIGATION_QUEUED
    active = session.execute(select(WorkTask).join(TaskConsumer, TaskConsumer.task_id == WorkTask.id)
        .where(TaskConsumer.case_id == case.id, TaskConsumer.active.is_(True), WorkTask.task_type.in_(HANDLERS))).scalars().all()
    assert len(active) == 2
    assert next(row for row in active if row.task_type == "INVESTIGATE_TECHNOLOGY").status == "COMPLETED"
    assert next(row for row in active if row.task_type == "INVESTIGATE_TRANSACTION").status == "WAITING_HANDLER"
    before = {row.id for row in active}
    OrchestrationService(session, settings).route_case(case)
    session.commit()
    after = session.execute(select(WorkTask.id).join(TaskConsumer, TaskConsumer.task_id == WorkTask.id)
        .where(TaskConsumer.case_id == case.id, TaskConsumer.active.is_(True), WorkTask.task_type.in_(HANDLERS))).scalars().all()
    assert set(after) == before
    for row in work:
        session.refresh(row)
        assert row.result is not None

def test_supervisor_disagreement_cannot_be_overruled(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings)
    contradictory = next(row for row in work if row.task_type == "INVESTIGATE_TRANSACTION")
    contradictory.result = {**contradictory.result, "findings": [
        {**contradictory.result["findings"][0], "expected_value": "SUCCESS", "assessment": "SUPPORTED"}]}
    session.commit()
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "ESCALATE"
    assert any("Unsupported" in issue for issue in result["unresolved_issues"])
    session.refresh(case)
    assert case.status == CaseState.ESCALATED

def test_supervisor_cycle_budget(session, settings):
    settings.supervisor_max_review_cycles = 1
    case, task, runner, claim, work = claimed_review(session, settings, FakeSupervisor("REINVESTIGATE"))
    session.add(SupervisorReview(id=uuid4().hex, task_id=task.id, case_id=case.id, attempt=99,
        outcome="REINVESTIGATE", model="historical-test", prompt_version="supervisor-1.0",
        created_at=datetime.now(timezone.utc), snapshot={}, result={}, telemetry={}))
    session.commit()
    assert runner.run(task.id, "supervisor", claim["lease_token"])["outcome"] == "ESCALATE"

def test_supervisor_independent_source_integrity(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings)
    evidence = session.get(Evidence, work[0].result["evidence_references"][0]["evidence_id"])
    evidence.payload = {"made_up": "not in source"}
    session.commit()
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "FAILED" and result["error_code"] == "supervisor_source_mismatch"

def test_supervisor_stale_worker_rejected(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings)
    task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    with pytest.raises(LeaseLost):
        runner.run(task.id, "supervisor", claim["lease_token"])
    assert not session.scalar(select(func.count()).select_from(SupervisorReview))

def test_supervisor_changed_context_during_model(session, settings):
    def change():
        with runner.database.get_session() as other:
            current = other.get(Case, case.id)
            current.orchestration_generation += 1
            other.commit()
    case, task, runner, claim, work = claimed_review(session, settings, FakeSupervisor(mutate=change))
    with pytest.raises(LeaseLost):
        runner.run(task.id, "supervisor", claim["lease_token"])
    assert not session.scalar(select(func.count()).select_from(SupervisorReview))

def test_supervisor_timeout_retry_and_audit(session, settings):
    case, task, runner, claim, work = claimed_review(session, settings, FakeSupervisor(error=TimeoutError()))
    assert runner.run(task.id, "supervisor", claim["lease_token"])["outcome"] == "FAILED"
    session.refresh(task)
    assert task.status == "RETRY_WAIT"
    audit = session.scalar(select(AuditLog).where(AuditLog.entity_id == task.id, AuditLog.event_type == "supervisor_failed"))
    assert audit.details["model"] and claim["lease_token"] not in json.dumps(audit.details)

def test_supervisor_worker_path(session, settings):
    case, task, database, work = investigated(session, settings)
    assert run_once(database, "supervisor-worker", settings, supervisor_provider=FakeSupervisor())["claimed"] == 1
    session.refresh(task)
    assert task.result["outcome"] == "RECOMMENDATION"

def test_supervisor_new_conflicting_source_cannot_recommend(session, settings):
    from app.ingestion.models import EventRecord
    case, task, runner, claim, work = claimed_review(session, settings)
    ref = work[0].result["evidence_references"][0]
    original = session.get(EventRecord, ref["event_record_id"])
    now = datetime.now(timezone.utc)
    session.add(EventRecord(id=uuid4().hex, event_id=uuid4().hex,
        source_system=original.source_system, event_type=original.event_type,
        entity_reference=original.entity_reference, correlation_id=original.correlation_id,
        source_record_reference=original.source_record_reference, schema_version="1.0",
        occurred_at=now, ingested_at=now,
        payload={**original.payload, "payment_status": "SUCCESS", "status_code": 200}))
    session.commit()
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    assert result["outcome"] == "ESCALATE"
    assert any("Superseded" in issue for issue in result["unresolved_issues"])
