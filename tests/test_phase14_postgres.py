from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, InternalError
from fastapi.testclient import TestClient
from test_phase6_postgres import postgres_engine, session, settings, source_case
from test_phase9_postgres import fixture_case, evaluate, WORKER, REVIEWER
from test_phase10_postgres import queued, claim, execute
from app.database import DatabaseManager
from app.reliability.service import ShadowService
from app.reliability.replay import ReplayService
from app.reliability.models import ShadowEvaluation
from app.reliability.contracts import ShadowRequest
from app.intelligence.contracts import AnalyticsAccess
from app.controls.service import Controls
from app.controls.models import ControlAuthorization, ActionApproval
from app.models.domain import Case, ActionRecord, HumanApproval, Decision, VerificationResult, Evidence
from app.simulator.models import SyntheticPayment, SyntheticLedgerEntry, SyntheticConfirmationEvent
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.execution.service import ExecutionEngine
from app.main import create_app


def shadow(session, settings, parts):
    case, review, version, action, _, _ = parts
    database = DatabaseManager(session.get_bind().url)
    return ShadowService(database, settings).evaluate(case.id, ShadowRequest(supervisor_review_id=review.id,
        policy_version_id=version.id, action=action), AnalyticsAccess(REVIEWER))


@pytest.mark.parametrize("human,expected", [(False, "WOULD_AUTO_ELIGIBLE"), (True, "WOULD_HUMAN_APPROVAL_REQUIRED")])
def test_shadow_shared_rules_but_no_operational_mutations(session, settings, human, expected):
    parts = fixture_case(session, human)
    before = [session.scalar(select(func.count()).select_from(m)) for m in (ControlAuthorization, ActionApproval, ActionRecord, HumanApproval, Decision, SyntheticConfirmationEvent)]
    result = shadow(session, settings, parts)
    assert result.outcome == expected and result.execution_permitted is False
    assert result.action_authorization == "NOT_EVALUATED"
    assert before == [session.scalar(select(func.count()).select_from(m)) for m in (ControlAuthorization, ActionApproval, ActionRecord, HumanApproval, Decision, SyntheticConfirmationEvent)]
    session.refresh(parts[0]); session.refresh(parts[4]); session.refresh(parts[5])
    assert parts[0].status.value == "AWAITING_DECISION"
    assert parts[4].amount == parts[5].amount == 100 and parts[5].balance_after == 900
    assert session.scalar(select(func.count()).select_from(ShadowEvaluation)) == 1
    comparison = ShadowService(DatabaseManager(session.get_bind().url), settings).comparison(parts[0].id, AnalyticsAccess(REVIEWER))
    assert comparison["independently_verified_resolution"] is False
    assert comparison["execution_permitted"] is False and len(comparison["shadow_results"]) == 1


def test_shadow_idempotency_and_no_usable_authorization(session, settings):
    parts = fixture_case(session)
    first, second = shadow(session, settings, parts), shadow(session, settings, parts)
    assert first.id == second.id
    with pytest.raises(LookupError): ExecutionEngine(session, settings).submit(first.id, WORKER)
    with pytest.raises(LookupError): Controls(session).current(first.id)


@pytest.mark.parametrize("mutation", ["stale_source", "inactive_policy", "unsupported_conclusion"])
def test_shadow_fail_closed_shared_preconditions(session, settings, mutation):
    parts = fixture_case(session)
    if mutation == "stale_source": parts[4].status = "PENDING"
    if mutation == "inactive_policy": parts[2].is_active = False
    if mutation == "unsupported_conclusion": parts[1].result = {**parts[1].result, "supported_conclusions": []}
    session.commit()
    result = shadow(session, settings, parts)
    assert result.outcome == "WOULD_BLOCK" and result.result["reasons"]
    assert session.scalar(select(func.count()).select_from(ControlAuthorization)) == 0


def test_readonly_control_object_cannot_authorize_or_approve(session):
    inspector = Controls(session, read_only=True)
    with pytest.raises(PermissionError): inspector.evaluate("x", "x", "x", {}, WORKER)
    with pytest.raises(PermissionError): inspector.approve("x", REVIEWER, "APPROVE", "x")
    with pytest.raises(PermissionError): inspector.current("x")


def test_postgres_readonly_transaction_blocks_unexpected_write(postgres_engine):
    with Session(postgres_engine) as other:
        other.execute(text("SET TRANSACTION READ ONLY"))
        with pytest.raises(InternalError): other.execute(text("UPDATE cases SET summary = 'forbidden'"))
        other.rollback()


def test_shadow_database_constraint_rejects_execution_permission(session, settings):
    result = shadow(session, settings, fixture_case(session))
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE shadow_evaluations SET execution_permitted = true WHERE id=:id"), {"id": result.id})
        session.commit()
    session.rollback()


def test_replay_later_confirmation_never_known_earlier(session):
    case, exception = source_case(session)
    cutoff = session.scalar(select(func.clock_timestamp()))
    event = EventRecord(id=uuid4().hex, event_id=uuid4().hex, source_system="confirmations", event_type="payment.confirmed",
        entity_reference=exception.source_reference, source_record_reference="late", schema_version="1.0",
        occurred_at=cutoff + timedelta(seconds=10), ingested_at=cutoff + timedelta(seconds=11),
        payload={"confirmation_status": "CONFIRMED", "expected_root_cause": "HIDDEN"})
    session.add(event); session.flush()
    session.add(ExceptionEvidence(id=uuid4().hex, exception_id=exception.id, event_record_id=event.id, linked_at=cutoff + timedelta(seconds=12)))
    session.commit()
    result = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(case.id, cutoff)
    assert event.id not in {e["id"] for e in result.evidence_known_at_time}
    assert event.id in {e["id"] for e in result.evidence_observed_later}
    assert "expected_root_cause" not in result.model_dump_json()


def test_replay_link_time_and_invalid_provenance(session):
    case, exception = source_case(session)
    cutoff = session.scalar(select(func.clock_timestamp()))
    link = session.scalar(select(ExceptionEvidence).where(ExceptionEvidence.exception_id == exception.id))
    link.linked_at = cutoff + timedelta(seconds=1)
    for evidence in session.scalars(select(Evidence).where(Evidence.case_id == case.id)):
        if (evidence.integrity_metadata or {}).get("event_record_id") == link.event_record_id:
            evidence.retrieval_timestamp = cutoff + timedelta(seconds=1)
    session.add(Evidence(id=uuid4().hex, case_id=case.id, source_system="legacy", source_record_id="unknown", payload={"confirmation_status": "CONFIRMED"}))
    session.commit()
    report = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(case.id, cutoff)
    assert link.event_record_id not in {e["id"] for e in report.evidence_known_at_time}
    assert all(e["source_system"] != "legacy" for e in report.evidence_known_at_time)


def test_replay_approval_after_cutoff_not_in_past(session):
    parts = fixture_case(session, human=True)
    authorization = evaluate(session, parts)
    cutoff = session.scalar(select(func.clock_timestamp()))
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization["id"]))
    Controls(session).approve(approval.id, REVIEWER, "APPROVE", "Synthetic decision")
    report = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(parts[0].id, cutoff)
    assert not any(e["kind"] == "ACTION_APPROVAL_APPROVE" for e in report.timeline)
    present = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(parts[0].id)
    assert any(e["kind"] == "ACTION_APPROVAL_APPROVE" for e in present.timeline)


def test_replay_verified_execution_and_simulation_are_distinct(session, settings):
    parts, _, _, database = queued(session, settings)
    execute(database, settings, claim(session, settings)); execute(database, settings, claim(session, settings))
    report = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(parts[0].id)
    kinds = {e["kind"] for e in report.timeline}
    assert {"SIMULATED", "synthetic_confirmation_replayed", "INDEPENDENT_VERIFICATION"}.issubset(kinds)
    assert any(e["basis"] == "HYPOTHETICAL" for e in report.timeline if e["kind"] == "SIMULATED")
    comparison = ShadowService(database, settings).comparison(parts[0].id, AnalyticsAccess(REVIEWER))
    assert comparison["independently_verified_resolution"] is True


def test_replay_scope_and_unknown_case(session):
    case, _ = source_case(session)
    with pytest.raises(PermissionError): ReplayService(session, AnalyticsAccess(REVIEWER, frozenset())).replay(case.id)
    with pytest.raises(LookupError): ReplayService(session, AnalyticsAccess(REVIEWER)).replay("unknown")
    with pytest.raises(ValueError): ReplayService(session, AnalyticsAccess(REVIEWER)).replay(case.id, case.created_at - timedelta(seconds=1))


def test_protected_shadow_api_forbids_client_authority(session, settings, monkeypatch):
    parts = fixture_case(session)
    monkeypatch.setenv("DATABASE_URL", session.get_bind().url.render_as_string(hide_password=False))
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", "w" * 32)
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", "r" * 32)
    request = {"supervisor_review_id": parts[1].id, "policy_version_id": parts[2].id, "action": parts[3].model_dump()}
    url = f"/api/v1/reliability/cases/{parts[0].id}/shadow"
    with TestClient(create_app()) as client:
        assert client.post(url, json=request).status_code == 401
        assert client.post(url, json={**request, "execution_permitted": True}, headers={"Authorization": "Bearer " + "r" * 32}).status_code == 422
        response = client.post(url, json=request, headers={"Authorization": "Bearer " + "r" * 32})
        assert response.status_code == 200 and response.json()["execution_permitted"] is False
        replay = client.get(f"/api/v1/reliability/cases/{parts[0].id}/replay", headers={"Authorization": "Bearer " + "r" * 32})
        assert replay.status_code == 200


def test_optional_ml_is_not_a_control_input(session, settings, monkeypatch):
    import app.ml.benchmark
    monkeypatch.setattr(app.ml.benchmark, "compare", lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("unavailable experimental ML")))
    result = shadow(session, settings, fixture_case(session))
    assert result.outcome == "WOULD_AUTO_ELIGIBLE"


def test_concurrent_shadow_results_are_idempotent(session, settings):
    from concurrent.futures import ThreadPoolExecutor
    parts = fixture_case(session)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: shadow(session, settings, parts), range(2)))
    assert results[0].id == results[1].id
    assert session.scalar(select(func.count()).select_from(ShadowEvaluation)) == 1
    assert session.scalar(select(func.count()).select_from(ControlAuthorization)) == 0


def test_earlier_retrieval_establishes_availability_despite_late_link(session):
    case, exception = source_case(session)
    cutoff = session.scalar(select(func.clock_timestamp()))
    link = session.scalar(select(ExceptionEvidence).where(ExceptionEvidence.exception_id == exception.id))
    link.linked_at = cutoff + timedelta(seconds=1)
    session.commit()
    report = ReplayService(session, AnalyticsAccess(REVIEWER)).replay(case.id, cutoff)
    assert link.event_record_id in {e["id"] for e in report.evidence_known_at_time}
    assert link.event_record_id not in {e["id"] for e in report.evidence_observed_later}
