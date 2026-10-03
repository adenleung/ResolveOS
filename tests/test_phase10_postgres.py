from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from test_phase6_postgres import postgres_engine, session
from test_phase9_postgres import fixture_case, evaluate, WORKER, REVIEWER
from app.config import Settings
from app.controls.models import ActionApproval
from app.controls.service import Controls
from app.database import DatabaseManager
from app.domain.case_service import CaseState
from app.execution.models import CounterfactualSimulation, ExecutionOperation
from app.execution.service import ExecutionEngine, EXECUTION_HANDLERS
from app.ingestion.models import EventRecord
from app.models.domain import ActionRecord, AuditLog, Case, VerificationResult
from app.orchestration.models import WorkTask
from app.orchestration.models import WorkflowReview
from app.orchestration.queue import LeaseLost, WorkQueue
from app.orchestration.worker import run_once
from app.simulator.models import SyntheticConfirmationEvent, SyntheticLedgerEntry

@pytest.fixture
def settings():
    return Settings(orchestration_lease_seconds=30)

def queued(session, settings, human=False):
    parts = fixture_case(session, human)
    result = evaluate(session, parts)
    assert result["outcome"] == ("HUMAN_APPROVAL_REQUIRED" if human else "AUTO_ELIGIBLE"), result["reasons"]
    if human:
        approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == result["id"]))
        Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Confirmation-only synthetic effect approved")
    submitted = ExecutionEngine(session, settings).submit(result["id"], WORKER)
    return parts, result, submitted, DatabaseManager(session.get_bind().url)

def claim(session, settings, owner="execution-worker"):
    claimed = WorkQueue(session, settings, handlers=EXECUTION_HANDLERS).claim(owner)[0]
    session.commit()
    return claimed

def execute(database, settings, claimed, owner="execution-worker", fault=None):
    with database.get_session() as other:
        return ExecutionEngine(other, settings).execute(claimed["id"], owner, claimed["lease_token"], fault=fault)

@pytest.mark.parametrize("human", [False, True])
def test_actual_confirmation_replay_and_independent_verification(session, settings, human):
    parts, authorization, submitted, database = queued(session, settings, human)
    first = claim(session, settings)
    result = execute(database, settings, first)
    assert result["outcome"] == "EFFECT_COMMITTED"
    session.refresh(parts[0])
    assert parts[0].status == CaseState.VERIFYING
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id)) == 1
    second = claim(session, settings)
    result = execute(database, settings, second)
    assert result["outcome"] == "VERIFIED"
    session.refresh(parts[0]); session.refresh(parts[4]); session.refresh(parts[5])
    assert parts[0].status == CaseState.RESOLVED
    assert parts[4].amount == 100 and parts[5].amount == 100 and parts[5].balance_after == 900
    verification = session.scalar(select(VerificationResult).where(VerificationResult.action_id == submitted["action_id"]))
    assert verification.success and verification.observed_state["processing_status"] == "PROCESSED"

def test_unapproved_action_cannot_submit(session, settings):
    parts = fixture_case(session, True)
    authorization = evaluate(session, parts)
    with pytest.raises(ValueError, match="approval_required"):
        ExecutionEngine(session, settings).submit(authorization["id"], WORKER)
    session.rollback()
    assert not session.scalar(select(ExecutionOperation).where(ExecutionOperation.case_id == parts[0].id))

def test_duplicate_submission_one_effect(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    repeat = ExecutionEngine(session, settings).submit(authorization["id"], WORKER)
    assert repeat["operation_id"] == submitted["operation_id"]
    claimed = claim(session, settings)
    execute(database, settings, claimed)
    with pytest.raises(LeaseLost): execute(database, settings, claimed)
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id)) == 1

def test_partial_failure_rolls_back_effect_and_case(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    claimed = claim(session, settings)
    def fault(): raise RuntimeError("injected_precommit_crash")
    with pytest.raises(RuntimeError): execute(database, settings, claimed, fault=fault)
    session.refresh(parts[0])
    assert parts[0].status == CaseState.AWAITING_DECISION
    assert not session.scalar(select(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id))
    assert not session.scalar(select(EventRecord).where(EventRecord.source_system == "confirmations", EventRecord.entity_reference == parts[3].payment_id))
    # The committed claim survives; retrying the same still-valid fence is safe.
    assert execute(database, settings, claimed)["outcome"] == "EFFECT_COMMITTED"

def test_expired_lease_rolls_back_partial_effect(session, settings):
    settings.orchestration_lease_seconds = 1
    parts, authorization, submitted, database = queued(session, settings)
    claimed = claim(session, settings)
    with pytest.raises(LeaseLost): execute(database, settings, claimed, fault=lambda: time.sleep(1.1))
    assert not session.scalar(select(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id))
    session.refresh(parts[0])
    assert parts[0].status == CaseState.AWAITING_DECISION

@pytest.mark.parametrize("change", ["ledger", "duplicate", "confirmation", "event"])
def test_failed_independent_verification_never_resolves(session, settings, change):
    parts, authorization, submitted, database = queued(session, settings)
    execute(database, settings, claim(session, settings))
    if change == "ledger": parts[5].amount = 200
    if change == "duplicate": session.add(SyntheticLedgerEntry(id=uuid4().hex, payment_id=parts[4].id,
        ledger_transaction_id=uuid4().hex, entry_type="DEBIT", amount=100, currency="SGD", balance_after=800, status="POSTED"))
    if change == "confirmation":
        confirmation = session.scalar(select(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id))
        confirmation.status = "FAILED"
    if change == "event":
        observed = session.scalar(select(EventRecord).where(EventRecord.source_system == "confirmations", EventRecord.entity_reference == parts[3].payment_id))
        observed.payload = {"confirmation_status": "FAILED"}
    session.commit()
    result = execute(database, settings, claim(session, settings))
    assert result["outcome"] == "FAILED_VERIFICATION" and result["discrepancies"]
    session.refresh(parts[0])
    assert parts[0].status == CaseState.ESCALATED
    assert session.scalar(select(WorkflowReview).where(WorkflowReview.case_id == parts[0].id)) is not None

def test_revoked_approval_checked_at_execution(session, settings):
    parts, authorization, submitted, database = queued(session, settings, True)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization["id"]))
    Controls(session).approve(approval.id, REVIEWER, "REVOKE", "Approval withdrawn before execution")
    with pytest.raises(ValueError, match="approval_required"):
        execute(database, settings, claim(session, settings))
    assert not session.scalar(select(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == parts[4].id))

def test_worker_recovery_and_verification_path(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    stale = claim(session, settings, "crashed-worker")
    task = session.get(WorkTask, stale["id"])
    task.lease_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    session.commit()
    queue = WorkQueue(session, settings, handlers=EXECUTION_HANDLERS)
    queue.recover()
    session.flush()
    task.scheduled_at = queue.now()
    session.commit()
    assert run_once(database, "replacement", settings)["claimed"] == 1
    with pytest.raises(LeaseLost): execute(database, settings, stale, "crashed-worker")
    assert run_once(database, "verifier", settings)["claimed"] == 1
    session.refresh(parts[0])
    assert parts[0].status == CaseState.RESOLVED
    assert session.scalar(select(AuditLog).where(AuditLog.case_id == parts[0].id,
        AuditLog.event_type == "synthetic_action_verified"))


@pytest.mark.parametrize("verification", [False, True])
@pytest.mark.parametrize("failure_kind", ["error", "crash", "deadline"])
def test_exhausted_execution_recovery_escalates_durably(session, settings, verification, failure_kind):
    parts, authorization, submitted, database = queued(session, settings)
    if verification:
        execute(database, settings, claim(session, settings))
    claimed = claim(session, settings)
    task = session.get(WorkTask, claimed["id"])
    task.max_attempts = task.attempt_count
    session.commit()
    queue = WorkQueue(session, settings)
    if failure_kind == "crash":
        task.lease_expires_at = queue.now() - timedelta(seconds=1)
        session.commit()
        queue.recover()
    elif failure_kind == "deadline":
        task.deadline = queue.now() - timedelta(seconds=1)
        session.commit()
        queue.expire_deadlines()
    else:
        queue.fail(task.id, "execution-worker", claimed["lease_token"], "injected_transient_failure", True)
    session.commit()
    # Simulate interruption after durable failure, before projecting its outcome.
    assert task.status == "DEAD_LETTER"
    with database.get_session() as other:
        assert ExecutionEngine(other, settings).reconcile_terminal() == 1
        assert ExecutionEngine(other, settings).reconcile_terminal() == 0
    session.refresh(parts[0])
    operation = session.get(ExecutionOperation, submitted["operation_id"])
    action = session.get(ActionRecord, submitted["action_id"])
    expected = "VERIFICATION_UNCERTAIN" if verification else "FAILED_EXECUTION"
    assert operation.status == action.status == expected
    assert parts[0].status == CaseState.ESCALATED
    assert session.scalar(select(WorkflowReview).where(WorkflowReview.case_id == parts[0].id)) is not None
    assert session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.case_id == parts[0].id, AuditLog.event_type == "synthetic_execution_terminal_failure")) == 1
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == int(verification)
    assert session.scalar(select(func.count()).select_from(VerificationResult)) == 0
    with pytest.raises(LeaseLost): execute(database, settings, claimed)
    with pytest.raises(LeaseLost): queue.fail(task.id, "execution-worker", claimed["lease_token"], "stale", False)
    session.rollback()


def test_interrupted_reconciliation_rolls_back_then_recovers(session, settings, monkeypatch):
    parts, authorization, submitted, database = queued(session, settings)
    claimed = claim(session, settings)
    WorkQueue(session, settings).fail(claimed["id"], "execution-worker", claimed["lease_token"], "fatal", False)
    session.commit()
    with database.get_session() as other:
        engine = ExecutionEngine(other, settings)
        original = engine.workflow.audit
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("reconciliation_crash")
        monkeypatch.setattr(engine.workflow, "audit", interrupted)
        with pytest.raises(RuntimeError, match="reconciliation_crash"):
            engine.reconcile_terminal()
        other.rollback()
    assert session.get(ExecutionOperation, submitted["operation_id"]).status == "QUEUED"
    run_once(database, "recovery", settings)
    session.refresh(parts[0])
    session.expire_all()
    assert session.get(ExecutionOperation, submitted["operation_id"]).status == "FAILED_EXECUTION"
    assert parts[0].status == CaseState.ESCALATED


def test_worker_reconciles_revoked_authorization(session, settings):
    parts, authorization, submitted, database = queued(session, settings, True)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization["id"]))
    Controls(session).approve(approval.id, REVIEWER, "REVOKE", "Withdrawn")
    assert run_once(database, "worker", settings)["claimed"] == 1
    session.expire_all()
    assert session.get(ExecutionOperation, submitted["operation_id"]).status == "FAILED_EXECUTION"
    assert parts[0].status == CaseState.ESCALATED
    assert not session.scalar(select(SyntheticConfirmationEvent))


def test_concurrent_terminal_reconciliation_is_idempotent(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    claimed = claim(session, settings)
    WorkQueue(session, settings).fail(claimed["id"], "execution-worker", claimed["lease_token"], "fatal", False)
    session.commit()
    def reconcile(_):
        with database.get_session() as other:
            return ExecutionEngine(other, settings).reconcile_terminal()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reconcile, range(2))) == 1
    assert session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.case_id == parts[0].id, AuditLog.event_type == "synthetic_execution_terminal_failure")) == 1


# Phase 10 extension: model-free counterfactual projection; never bypasses controls.
def test_policy_change_blocks_simulated_execution_before_effect(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    parts[2].content = {**parts[2].content, "max_amount": "50"}
    session.commit()
    with pytest.raises(ValueError, match="authorization_stale"):
        execute(database, settings, claim(session, settings))
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 0
    assert session.get(ExecutionOperation, submitted["operation_id"]).status == "QUEUED"
    session.refresh(parts[0])
    assert parts[0].status == CaseState.AWAITING_DECISION


def test_concurrent_simulated_execution_commits_one_effect(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    claimed = claim(session, settings)
    session.commit()
    def contend(_):
        try:
            return execute(database, settings, claimed)["outcome"]
        except LeaseLost:
            return "FENCED"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contend, range(2))) == ["EFFECT_COMMITTED", "FENCED"]
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 1
    assert session.scalar(select(func.count()).select_from(EventRecord).where(
        EventRecord.source_system == "confirmations")) == 1
    assert execute(database, settings, claim(session, settings))["outcome"] == "VERIFIED"
    session.refresh(parts[0])
    assert parts[0].status == CaseState.RESOLVED


def test_counterfactual_preview_persists_without_approval_or_effect(session, settings):
    parts = fixture_case(session, True)
    authorization = evaluate(session, parts)
    report = ExecutionEngine(session, settings).preview(authorization["id"], WORKER)
    assert report["outcome"] == "PASS" and report["hypothetical_only"] is True
    assert report["operation_id"] is None
    assert report["projection"]["expected"]["additional_payment_count"] == 0
    assert report["projection"]["expected"]["additional_ledger_entry_count"] == 0
    assert session.get(CounterfactualSimulation, report["id"]) is not None
    assert session.scalar(select(func.count()).select_from(ActionRecord)) == 0
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 0
    with pytest.raises(ValueError, match="approval_required"):
        ExecutionEngine(session, settings).submit(authorization["id"], WORKER)
    session.rollback()


def test_queued_execution_has_immutable_simulation_provenance(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    simulation = session.get(CounterfactualSimulation, submitted["simulation_id"])
    operation = session.get(ExecutionOperation, submitted["operation_id"])
    assert simulation.operation_id == operation.id
    assert simulation.outcome == simulation.projection["outcome"] == "PASS"
    assert simulation.projection["expected"]["confirmation"] == {"event_id": operation.event_id, "status": "CONFIRMED"}
    assert ExecutionEngine(session, settings).submit(authorization["id"], WORKER)["simulation_id"] == simulation.id
    assert session.scalar(select(func.count()).select_from(CounterfactualSimulation).where(
        CounterfactualSimulation.operation_id == operation.id)) == 1
    assert execute(database, settings, claim(session, settings))["outcome"] == "EFFECT_COMMITTED"
    assert execute(database, settings, claim(session, settings))["outcome"] == "VERIFIED"


def test_changed_source_blocks_simulated_execution_before_effect(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    parts[4].status = "HOLD"
    session.commit()
    with pytest.raises(ValueError, match="authorization_stale"):
        execute(database, settings, claim(session, settings))
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 0
    assert session.get(ExecutionOperation, submitted["operation_id"]).status == "QUEUED"


def test_tampered_projection_blocks_execution_before_effect(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    simulation = session.get(CounterfactualSimulation, submitted["simulation_id"])
    simulation.projection = {**simulation.projection, "source_hash": "fabricated-source-hash"}
    session.commit()
    with pytest.raises(ValueError, match="counterfactual_simulation_stale_or_blocked"):
        execute(database, settings, claim(session, settings))
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 0


def test_simulation_and_observed_state_divergence_escalates(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    assert execute(database, settings, claim(session, settings))["outcome"] == "EFFECT_COMMITTED"
    simulation = session.get(CounterfactualSimulation, submitted["simulation_id"])
    simulation.projection = {**simulation.projection, "expected": {
        **simulation.projection["expected"], "event_processing_status": "FAILED"}}
    session.commit()
    outcome = execute(database, settings, claim(session, settings))
    assert outcome["outcome"] == "FAILED_VERIFICATION"
    assert "simulated_event_state_invalid" in outcome["discrepancies"]
    session.refresh(parts[0])
    assert parts[0].status == CaseState.ESCALATED
    assert session.scalar(select(WorkflowReview).where(WorkflowReview.case_id == parts[0].id)) is not None


def test_revoked_human_approval_cannot_be_bypassed_by_preview(session, settings):
    parts = fixture_case(session, True)
    authorization = evaluate(session, parts)
    preview = ExecutionEngine(session, settings).preview(authorization["id"], WORKER)
    assert preview["outcome"] == "PASS"
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization["id"]))
    Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Synthetic only")
    submitted = ExecutionEngine(session, settings).submit(authorization["id"], WORKER)
    Controls(session).approve(approval.id, REVIEWER, "REVOKE", "Withdrawn")
    with pytest.raises(ValueError, match="approval_required"):
        execute(DatabaseManager(session.get_bind().url), settings, claim(session, settings))
    assert session.scalar(select(func.count()).select_from(SyntheticConfirmationEvent)) == 0
