from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func

from test_phase6_postgres import postgres_engine, session
from app.classification.service import ClassificationService
from app.config import Settings
from app.controls.contracts import ActionRequest
from app.controls.models import ActionApproval, ActionApprovalHistory, ControlAuthorization
from app.controls.service import Controls
from app.domain.case_service import CaseState
from app.ingestion.models import EventRecord
from app.ingestion.service import EventIngestionService
from app.models.domain import ActionRecord, AuditLog, Case, Evidence, ExceptionRecord, HumanApproval, Policy, PolicyVersion
from app.orchestration.auth import Identity
from app.orchestration.contracts import TaskType
from app.orchestration.service import OrchestrationService
from app.simulator.models import SyntheticConfirmationEvent, SyntheticLedgerEntry, SyntheticPayment
from app.supervisor.models import SupervisorReview

WORKER = Identity("test-worker", frozenset({"WORKER"}))
REVIEWER = Identity("test-reviewer", frozenset({"OPERATIONS_REVIEWER"}))

@pytest.fixture
def settings():
    return Settings()

def fixture_case(session, human=False):
    # Controls use PostgreSQL time. Seed synthetic observations with that same
    # clock so valid fixtures cannot become future evidence due to host skew.
    now = session.scalar(select(func.clock_timestamp()))
    payment_id = "control-payment-" + uuid4().hex
    key = uuid4().hex
    payment = SyntheticPayment(id=uuid4().hex, payment_id=payment_id, idempotency_key=key,
        amount=Decimal("100"), currency="SGD", beneficiary="synthetic", status="SETTLED",
        correlation_id=uuid4().hex, scenario_name="TEST_HIDDEN", expected_root_cause="TEST_HIDDEN")
    session.add(payment)
    session.flush()
    ledger = SyntheticLedgerEntry(id=uuid4().hex, payment_id=payment.id, ledger_transaction_id=uuid4().hex,
        entry_type="DEBIT", amount=100, currency="SGD", balance_after=900, status="POSTED")
    session.add(ledger)
    case = Case(id=uuid4().hex, case_number="CTRL-" + uuid4().hex, status=CaseState.AWAITING_DECISION,
        orchestration_generation=0)
    session.add(case)
    session.flush()
    exception = ExceptionRecord(id=uuid4().hex, case_id=case.id, exception_type="PAYMENT_CONFIRMATION_MISMATCH",
        description="Observed confirmation missing", severity="MEDIUM", source_reference=payment_id)
    session.add(exception)
    session.commit()
    records = [dict(event_id=uuid4().hex, source_system="payments", event_type="payment.recorded",
        entity_reference=payment_id, correlation_id=payment.correlation_id, occurred_at=now - timedelta(minutes=15),
        source_record_reference=payment_id, schema_version="1.0", payload={"payment_status": "SETTLED",
        "amount": "100", "currency": "SGD", "idempotency_key": key}),
        dict(event_id=uuid4().hex, source_system="ledger", event_type="ledger.entry_recorded",
        entity_reference=payment_id, correlation_id=payment.correlation_id, occurred_at=now - timedelta(minutes=15),
        source_record_reference=ledger.ledger_transaction_id, schema_version="1.0", payload={"ledger_status": "POSTED",
        "entry_type": "DEBIT", "amount": "100", "currency": "SGD", "ledger_transaction_id": ledger.ledger_transaction_id})]
    EventIngestionService(session).ingest(records)
    for observed in session.scalars(select(EventRecord).where(EventRecord.entity_reference == payment_id)):
        observed.ingested_at = now
    session.commit()
    ClassificationService(session).evaluate(exception.id)
    service = OrchestrationService(session)
    assessments = service.assessments([case.id])
    task = service.queue.schedule(service.payload(case, TaskType.REQUEST_SUPERVISOR_REVIEW, assessments), uuid4().hex)
    task.status = "COMPLETED"
    session.commit()
    event = session.scalar(select(EventRecord).where(EventRecord.entity_reference == payment_id, EventRecord.source_system == "payments"))
    evidence = Evidence(id=uuid4().hex, case_id=case.id, source_system="payments", source_record_id=payment_id,
        relevant_event_timestamp=event.occurred_at, payload=event.payload,
        integrity_metadata={"event_record_id": event.id, "as_of": now.isoformat()})
    session.add(evidence)
    review = SupervisorReview(id=uuid4().hex, task_id=task.id, case_id=case.id, attempt=1,
        outcome="RECOMMENDATION", model="test-supervisor-fixture", prompt_version="supervisor-1.0", created_at=now,
        snapshot={"generation": case.orchestration_generation, "assessment_ids": [row.id for row in assessments],
            "evidence_stamp": service.evidence_stamp(case), "issues": []}, telemetry={},
        result={"action_authorization": "NOT_EVALUATED", "proposed_action": "REPLAY_CONFIRMATION",
            "unresolved_issues": [], "evidence_ids": [evidence.id], "supported_conclusions": [
                {"field": "payment_status", "expected_value": "SETTLED", "assessment": "SUPPORTED", "evidence_ids": [evidence.id]}]})
    session.add(review)
    policy = Policy(id=uuid4().hex, name="synthetic-controls-" + uuid4().hex, active_version="1")
    session.add(policy)
    session.flush()
    version = PolicyVersion(id=uuid4().hex, policy_id=policy.id, version="1", is_active=True,
        effective_from=now - timedelta(days=1), content={"policy_schema": "synthetic-controls-1.0",
            "action_allowlist": ["REPLAY_CONFIRMATION"], "worker_roles": ["WORKER"], "approval_role": "OPERATIONS_REVIEWER",
            "max_amount": "1000", "currency": "SGD", "max_affected_cases": 10, "max_blast_radius": 1,
            "human_approval_required": human, "automatic_amount_limit": "500", "approval_ttl_seconds": 300,
            "authorization_ttl_seconds": 600, "effective_to": (now + timedelta(days=1)).isoformat(),
            "compensation": "NONE_CONFIRMATION_ONLY"})
    session.add(version)
    session.commit()
    action = ActionRequest(action_type="REPLAY_CONFIRMATION", payment_id=payment_id, idempotency_key=uuid4().hex)
    return case, review, version, action, payment, ledger

def evaluate(session, parts, identity=WORKER):
    case, review, version, action, _, _ = parts
    return Controls(session).evaluate(case.id, review.id, version.id, action, identity)

def test_auto_eligibility_no_execution(session):
    parts = fixture_case(session)
    result = evaluate(session, parts)
    assert result["outcome"] == "AUTO_ELIGIBLE"
    assert session.scalar(select(func.count()).select_from(ActionRecord)) == 0
    assert session.scalar(select(func.count()).select_from(HumanApproval)) == 0
    assert "TEST_HIDDEN" not in str(result)
    Controls(session).current(result["id"])

def test_control_idempotency(session):
    parts = fixture_case(session)
    first = evaluate(session, parts)
    second = evaluate(session, parts)
    assert first["id"] == second["id"]

def test_human_approval_bound_to_action(session):
    parts = fixture_case(session, human=True)
    result = evaluate(session, parts)
    assert result["outcome"] == "HUMAN_APPROVAL_REQUIRED"
    with pytest.raises(ValueError, match="approval_required"):
        Controls(session).current(result["id"])
    session.rollback()
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == result["id"]))
    Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Synthetic source reviewed")
    Controls(session).current(result["id"])
    assert session.get(HumanApproval, approval.human_approval_id).approved

@pytest.mark.parametrize("mutation", ["policy", "source", "state", "expiry", "recommendation"])
def test_stale_approval_rejected(session, mutation):
    parts = fixture_case(session, human=True)
    result = evaluate(session, parts)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == result["id"]))
    Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Reviewed")
    case, review, version, action, payment, ledger = parts
    if mutation == "policy": version.content = {**version.content, "max_amount": "50"}
    if mutation == "source": payment.status = "HOLD"
    if mutation == "state": case.status = CaseState.APPROVED
    if mutation == "expiry": approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if mutation == "recommendation": review.result = {**review.result, "proposed_action": "TRANSFER"}
    session.commit()
    with pytest.raises(ValueError): Controls(session).current(result["id"])

@pytest.mark.parametrize("failure", ["ledger", "amount", "confirmation", "duplicate", "unsupported", "policy_expired", "policy_missing"])
def test_fail_closed_preconditions(session, failure):
    parts = fixture_case(session)
    case, review, version, action, payment, ledger = parts
    if failure == "ledger": ledger.amount = 110
    if failure == "amount": version.content = {**version.content, "max_amount": "50"}
    if failure == "confirmation": session.add(SyntheticConfirmationEvent(id=uuid4().hex, payment_id=payment.id,
        event_id=uuid4().hex, status="CONFIRMED", occurred_at=datetime.now(timezone.utc), correlation_id=payment.correlation_id))
    if failure == "duplicate": session.add(SyntheticLedgerEntry(id=uuid4().hex, payment_id=payment.id,
        ledger_transaction_id=uuid4().hex, entry_type="DEBIT", amount=100, currency="SGD", balance_after=800, status="POSTED"))
    if failure == "unsupported": review.result = {**review.result, "supported_conclusions": []}
    if failure == "policy_expired": version.content = {**version.content, "effective_to": (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}
    session.commit()
    if failure == "policy_missing":
        result = Controls(session).evaluate(case.id, review.id, "missing-policy", action, WORKER)
    else: result = evaluate(session, parts)
    assert result["outcome"] == "BLOCKED" and result["reasons"]

def test_permissions_and_ai_cannot_approve(session):
    parts = fixture_case(session, human=True)
    with pytest.raises(PermissionError): evaluate(session, parts, REVIEWER)
    session.rollback()
    result = evaluate(session, parts)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == result["id"]))
    with pytest.raises(PermissionError): Controls(session).approve(approval.id, WORKER, "APPROVE", "AI says yes")
    with pytest.raises(ValidationError): ActionRequest(action_type="TRANSFER", payment_id=parts[3].payment_id, idempotency_key=uuid4().hex)

@pytest.mark.parametrize("operation", ["REJECT", "MORE_INVESTIGATION", "REVOKE"])
def test_approval_history_and_revocation(session, operation):
    parts = fixture_case(session, human=True)
    result = evaluate(session, parts)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == result["id"]))
    if operation == "REVOKE": Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Reviewed")
    Controls(session).approve(approval.id, REVIEWER, operation, "Explicit human decision")
    with pytest.raises(ValueError): Controls(session).current(result["id"])
    assert session.scalar(select(func.count()).select_from(ActionApprovalHistory).where(ActionApprovalHistory.approval_id == approval.id)) >= 1
    assert session.scalar(select(AuditLog).where(AuditLog.case_id == parts[0].id, AuditLog.event_type == "control_evaluated"))

def test_case_and_evidence_scope(session):
    parts = fixture_case(session)
    parts[1].result = {**parts[1].result, "evidence_ids": ["fabricated"]}
    session.commit()
    assert evaluate(session, parts)["outcome"] == "BLOCKED"

def test_real_supervisor_path_cannot_override_timeout(session, settings):
    from test_phase8_postgres import claimed_review, FakeSupervisor
    class Proposing(FakeSupervisor):
        def turn(self, *args):
            turn = super().turn(*args)
            turn.output.proposed_action = "REPLAY_CONFIRMATION"
            return turn
    settings.orchestration_lease_seconds = 30
    settings.investigator_token_budget = 50000
    case, task, runner, claim, work = claimed_review(session, settings, Proposing())
    result = runner.run(task.id, "supervisor", claim["lease_token"])
    review = session.scalar(select(SupervisorReview).where(SupervisorReview.task_id == task.id))
    payment_id = session.scalar(select(ExceptionRecord.source_reference).where(ExceptionRecord.case_id == case.id))
    action = ActionRequest(action_type="REPLAY_CONFIRMATION", payment_id=payment_id, idempotency_key=uuid4().hex)
    authorization = Controls(session).evaluate(case.id, review.id, "missing", action, WORKER)
    assert result["outcome"] == "RECOMMENDATION" and authorization["outcome"] == "BLOCKED"

def test_blast_radius_escalates(session):
    from app.models.domain import CaseIncident, Incident
    parts = fixture_case(session)
    parts[2].content = {**parts[2].content, "max_affected_cases": 1}
    other = Case(id=uuid4().hex, case_number=uuid4().hex, status=CaseState.DETECTED)
    incident = Incident(id=uuid4().hex, incident_key=uuid4().hex, incident_type="TECHNOLOGY",
        severity="HIGH", description="Synthetic shared impact", status="SUSPECTED")
    session.add_all([other, incident])
    session.flush()
    session.add_all([CaseIncident(id=uuid4().hex, case_id=case_id, incident_id=incident.id)
                     for case_id in (parts[0].id, other.id)])
    session.commit()
    # Review current shared context rather than bypassing the freshness requirement.
    parts[1].snapshot = {**parts[1].snapshot, "evidence_stamp": OrchestrationService(session).evidence_stamp(parts[0])}
    session.commit()
    assert evaluate(session, parts)["outcome"] == "ESCALATED"

def test_concurrent_authorization_same_logical_record(session):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    parts = fixture_case(session)
    def attempt():
        with Session(session.get_bind(), autoflush=False, expire_on_commit=False) as other:
            return Controls(other).evaluate(parts[0].id, parts[1].id, parts[2].id, parts[3], WORKER)["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: attempt(), range(2)))
    assert len(set(ids)) == 1

def test_control_api_role_and_request_boundaries(session, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    parts = fixture_case(session, human=True)
    worker_token, reviewer_token = uuid4().hex, uuid4().hex
    monkeypatch.setenv("DATABASE_URL", session.get_bind().url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", worker_token)
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", reviewer_token)
    body = {"supervisor_review_id": parts[1].id, "policy_version_id": parts[2].id, "action": parts[3].model_dump()}
    with TestClient(create_app()) as client:
        path = f"/api/v1/cases/{parts[0].id}/controls/evaluate"
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, json=body, headers={"Authorization": "Bearer " + reviewer_token}).status_code == 403
        authorized = client.post(path, json=body, headers={"Authorization": "Bearer " + worker_token})
        assert authorized.status_code == 200 and authorized.json()["outcome"] == "HUMAN_APPROVAL_REQUIRED"
        assert client.post(path, json={**body, "role": "ADMIN"}, headers={"Authorization": "Bearer " + worker_token}).status_code == 422
