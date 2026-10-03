from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_phase6_postgres import postgres_engine, session, settings, source_case, drain
from app.intelligence.contracts import AnalyticsAccess
from app.intelligence.service import IntelligenceService, interval
from app.orchestration.auth import Identity
from app.models.domain import Case, CaseIncident, Incident, AuditLog, ActionRecord, HumanApproval
from app.orchestration.models import WorkTask, TaskHistory
from app.correlation.models import IncidentCorrelationHistory
from app.classification.models import AssessmentHistory
from app.main import create_app

READER = Identity("reader", frozenset({"OPERATIONS_REVIEWER"}))


def service(session, grant=None):
    return IntelligenceService(session, AnalyticsAccess(READER, grant))


def test_observed_recurrence_and_hypothesis_evidence(session):
    first, _ = source_case(session)
    second, _ = source_case(session)
    report = service(session).report()
    api = next(row for row in report.systems if row.key == "api_gateway:/settle")
    assert api.count == 2 and set(api.case_ids) == {first.id, second.id}
    assert all(reference.kind == "event" for reference in api.references)
    assert report.hypotheses and "not proven" in report.hypotheses[0].confidence_limitation
    assert "TEST_HIDDEN" not in report.model_dump_json() and "expected_root_cause" not in report.model_dump_json()


def test_latest_assessment_does_not_double_count(session):
    case, exception = source_case(session)
    original = session.scalar(select(AssessmentHistory).where(AssessmentHistory.exception_id == exception.id))
    replacement = AssessmentHistory(id=uuid4().hex, exception_id=exception.id, case_id=case.id, revision=original.revision + 1,
        assessment_version=original.assessment_version, classification_source=original.classification_source,
        operational_eligible=True, change_reason="revision", assessment=original.assessment)
    session.add(replacement); session.commit()
    report = service(session).report()
    api = next(row for row in report.categories if row.key == "API_PROCESSING_FAILURE")
    assert api.count == 1 and api.references[0].id == replacement.id


def test_access_scope_and_empty_scope(session):
    first, _ = source_case(session)
    source_case(session)
    assert service(session, frozenset({first.id})).report().case_count == 1
    assert service(session, frozenset()).report().case_count == 0
    with pytest.raises(PermissionError):
        IntelligenceService(session, AnalyticsAccess(Identity("", frozenset())))


def test_incomplete_durations_not_completed(session):
    source_case(session)
    report = service(session).report()
    resolution = next(metric for metric in report.bottlenecks if metric.key == "total_independently_verified_resolution")
    assert resolution.completed == 0 and resolution.incomplete == report.case_count
    assert resolution.median_seconds is None and report.overview["verified_resolutions"] == 0


@pytest.mark.parametrize("offset,status", [(10, "completed"), (-10, "invalid_order"), (None, "incomplete")])
def test_interval_ordering(session, offset, status):
    now = session.scalar(select(func.clock_timestamp()))
    stop = now + timedelta(seconds=offset) if offset is not None else None
    seconds, result = interval(now, stop, now + timedelta(minutes=1))
    assert result == status
    assert (seconds is not None) == (status == "completed")


def test_future_completion_censored(session):
    now = session.scalar(select(func.clock_timestamp()))
    assert interval(now, now + timedelta(seconds=5), now)[1] == "incomplete"


def test_windows_and_truncation(session):
    source_case(session); source_case(session)
    report = service(session).report(case_limit=1)
    assert report.case_count == 1 and report.truncated
    now = report.generated_at
    for start, end in ((now, now), (now - timedelta(days=366), now), (now.replace(tzinfo=None), now)):
        with pytest.raises(ValueError): service(session).report(start, end)


def test_read_only_no_authorization_mutations(session):
    source_case(session)
    before = [session.scalar(select(func.count()).select_from(m)) for m in (Case, AuditLog, ActionRecord, HumanApproval)]
    service(session).report()
    assert before == [session.scalar(select(func.count()).select_from(m)) for m in (Case, AuditLog, ActionRecord, HumanApproval)]
    assert not session.new and not session.dirty


def test_repeated_escalation_and_missing_evidence(session):
    case, exception = source_case(session)
    for _ in range(2):
        session.add(AuditLog(id=uuid4().hex, case_id=case.id, entity_type="case", entity_id=case.id,
            event_type="orchestration_case_transition", summary="escalated", details={"current": "ESCALATED"}))
    assessment = session.scalar(select(AssessmentHistory).where(AssessmentHistory.exception_id == exception.id))
    assessment.assessment = {**assessment.assessment, "classification": {"categories": [], "uncertainty_flags": ["missing_evidence"]}}
    session.commit()
    report = service(session).report()
    assert next(r for r in report.recurrences if r.key == "escalation").count == 2
    assert next(r for r in report.recurrences if r.key == "classification_missing_evidence").count == 1


@pytest.mark.parametrize("operation", ["SPLIT", "MERGE"])
def test_incident_removed_memberships_and_contradictions_preserved(session, operation):
    case, _ = source_case(session)
    now = session.scalar(select(func.clock_timestamp()))
    incident = Incident(id=uuid4().hex, incident_key=uuid4().hex, incident_type="OBSERVED", description="suspected")
    session.add(incident); session.flush()
    history = IncidentCorrelationHistory(id=uuid4().hex, incident_id=incident.id, operation=operation, outcome=operation,
        rule_version="deterministic-correlation-1.0", case_ids=[case.id], shared_features=[], evidence_references=[],
        contradictions=[{"kind": "observed_identifier_disagreement"}], details={})
    session.add(history); session.flush()
    session.add(CaseIncident(id=uuid4().hex, case_id=case.id, incident_id=incident.id, removed_at=now,
        removal_reason="split", correlation_history_id=history.id)); session.commit()
    report = service(session).relationships(incident.id)
    assert report.case_ids == [] and report.memberships[0]["removal_reason"] == "split"
    assert report.history[0]["operation"] == operation and report.contradictions
    with pytest.raises(PermissionError): service(session, frozenset()).relationships(incident.id)


def test_unknown_incident(session):
    with pytest.raises(LookupError): service(session).relationships("missing")


@pytest.mark.parametrize("token,status", [(None, 401), ("invalid", 401), ("r" * 32, 200)])
def test_protected_typed_report_api(session, monkeypatch, token, status):
    monkeypatch.setenv("DATABASE_URL", session.get_bind().url.render_as_string(hide_password=False))
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", "w" * 32)
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", "r" * 32)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/intelligence/report", headers={"Authorization": "Bearer " + token} if token else {})
    assert response.status_code == status
    if status == 200: assert response.json()["action_authorization"] == "NOT_EVALUATED"


def test_production_development_auth_rejected(session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", session.get_bind().url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "production")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/intelligence/report").status_code == 503


def test_actual_verified_resolution_is_measured(session, settings):
    from test_phase10_postgres import queued, claim, execute
    parts, _, _, database = queued(session, settings)
    execute(database, settings, claim(session, settings))
    execute(database, settings, claim(session, settings))
    session.expire_all()
    report = service(session).report()
    assert report.overview["verified_resolutions"] == 1
    metric = next(m for m in report.bottlenecks if m.key == "total_independently_verified_resolution")
    assert metric.completed == 1 and metric.median_seconds >= 0
    assert next(m for m in report.bottlenecks if m.key == "execution_to_verification").completed == 1


def test_actual_approval_wait_and_rejection(session):
    from test_phase9_postgres import fixture_case, evaluate, REVIEWER
    from app.controls.models import ActionApproval
    from app.controls.service import Controls
    parts = fixture_case(session, human=True)
    authorization = evaluate(session, parts)
    approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization["id"]))
    metric = next(m for m in service(session).report().bottlenecks if m.key == "human_action_approval_wait")
    assert metric.completed == 0 and metric.incomplete == 1
    Controls(session).approve(approval.id, REVIEWER, "REJECT", "Synthetic review")
    metric = next(m for m in service(session).report().bottlenecks if m.key == "human_action_approval_wait")
    assert metric.completed == 1 and metric.median_seconds >= 0


def test_queue_and_attempt_duration_calculations(session, settings):
    from app.orchestration.service import OrchestrationService
    from app.investigation.models import InvestigationRun
    case, _ = source_case(session)
    OrchestrationService(session, settings).schedule_case(case.id)
    drain(session, settings)
    task = session.scalar(select(WorkTask).where(WorkTask.case_id == case.id, WorkTask.task_type == "INVESTIGATE_TECHNOLOGY"))
    now = session.scalar(select(func.clock_timestamp()))
    task.created_at = now - timedelta(seconds=20)
    session.add(TaskHistory(id=uuid4().hex, task_id=task.id, event_type="task_claimed", attempt_number=1, details={}, created_at=now - timedelta(seconds=10)))
    session.add(InvestigationRun(id=uuid4().hex, task_id=task.id, case_id=case.id, role="TECHNOLOGY", attempt=1,
        status="COMPLETED", model="synthetic", prompt_version="specialist-1.1", started_at=now - timedelta(seconds=10),
        completed_at=now - timedelta(seconds=2), context={}, telemetry={}))
    session.commit()
    report = service(session).report()
    assert next(m for m in report.bottlenecks if m.key == "investigation_queue_wait").median_seconds == 10
    assert next(m for m in report.bottlenecks if m.key == "investigation_attempt_duration").median_seconds == 8
