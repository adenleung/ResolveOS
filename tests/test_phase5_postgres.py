from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text, event as sqlalchemy_event
from sqlalchemy.orm import Session

from fastapi.testclient import TestClient
from app.main import app
from app.classification.models import AssessmentHistory
from app.classification.service import ClassificationService
from app.correlation.models import IncidentCorrelationHistory, IncidentCorrelationRun
from app.correlation.service import IncidentCorrelationService
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import DetectionHistory, EventRecord, ExceptionEvidence, IngestionError
from app.ingestion.service import EventIngestionService
from app.models.domain import AuditLog, Case, CaseIncident, Evidence, ExceptionRecord, Incident
from app.simulator.models import SyntheticPayment, SyntheticTechnologyLog
from app.simulator.service import SimulatorScenarioService


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        pytest.skip("Phase 5 integration tests require PostgreSQL via DATABASE_URL")
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def phase5_session(postgres_engine):
    with Session(postgres_engine) as session:
        owned_incident_ids = session.execute(
            select(Incident.id).where(
                Incident.incident_key.like("correlation-v1:%")
                | Incident.incident_key.like("phase5-%")
            )
        ).scalars().all()
        session.execute(delete(CaseIncident).where(CaseIncident.incident_id.in_(owned_incident_ids)))
        session.execute(delete(IncidentCorrelationHistory))
        session.execute(delete(IncidentCorrelationRun))
        session.execute(delete(Incident).where(Incident.id.in_(owned_incident_ids)))
        session.execute(delete(AssessmentHistory))
        session.execute(delete(ExceptionEvidence))
        session.execute(delete(DetectionHistory))
        detected_case_ids = session.execute(
            select(ExceptionRecord.case_id).where(ExceptionRecord.detection_key.is_not(None))
        ).scalars().all()
        session.execute(delete(Evidence).where(Evidence.case_id.in_(detected_case_ids)))
        session.execute(
            delete(AuditLog).where(
                AuditLog.event_type.in_(
                    [
                        "exception_detected",
                        "exception_evidence_updated",
                        "exception_classified",
                        "classification_revised",
                        "classification_evidence_updated",
                        "priority_changed",
                        "specialist_routing_changed",
                        "sla_recalculated",
                        "assessment_updated",
                        "incident_created_suspected",
                        "incident_case_associated",
                        "incident_case_disassociated",
                        "incident_status_changed",
                        "incident_split",
                        "incident_merged",
                        "incident_merged_into",
                    ]
                )
            )
        )
        session.execute(delete(ExceptionRecord).where(ExceptionRecord.detection_key.is_not(None)))
        session.execute(delete(Case).where(Case.id.in_(detected_case_ids)))
        session.execute(delete(Case).where(Case.external_ref.like("sim-payment-%")))
        session.execute(delete(EventRecord))
        session.execute(delete(IngestionError))
        session.execute(text("DELETE FROM sim_technology_logs"))
        session.execute(text("DELETE FROM sim_confirmation_events"))
        session.execute(text("DELETE FROM sim_ledger_entries"))
        session.execute(text("DELETE FROM sim_workflow_states"))
        session.execute(text("DELETE FROM sim_payments"))
        session.execute(text("DELETE FROM sim_policies"))
        session.commit()
        yield session


def _generate_api_failures(
    session: Session,
    count: int,
    incident_identifier: str | None = None,
    first_event_age: timedelta | None = None,
) -> list[dict[str, str]]:
    generated = []
    now = datetime.now(timezone.utc)
    for index in range(count):
        item = SimulatorScenarioService(session).generate_scenario("api_timeout", seed=uuid4().hex[:8])
        payment = session.execute(
            select(SyntheticPayment).where(SyntheticPayment.payment_id == item["payment_id"])
        ).scalar_one()
        log = session.execute(select(SyntheticTechnologyLog).where(SyntheticTechnologyLog.payment_id == payment.id)).scalar_one()
        log.response_body = {"incident_identifier": incident_identifier or f"observed-failure-{uuid4().hex}"}
        if index == 0 and first_event_age is not None:
            log = session.execute(
                select(SyntheticTechnologyLog).where(SyntheticTechnologyLog.payment_id == payment.id)
            ).scalar_one()
            log.occurred_at = now - first_event_age
        generated.append(item)
    session.commit()
    EventIngestionService(session).ingest_synthetic()
    ExceptionDetectionService(session).run()
    exceptions = session.execute(
        select(ExceptionRecord)
        .where(ExceptionRecord.detection_key.is_not(None))
        .order_by(ExceptionRecord.source_reference, ExceptionRecord.id)
    ).scalars().all()
    for exception in exceptions:
        ClassificationService(session).evaluate(exception.id)
    return generated


def _cases_for_payments(session: Session, generated: list[dict[str, str]]) -> list[str]:
    refs = [item["payment_id"] for item in generated]
    return list(
        session.execute(
            select(ExceptionRecord.case_id)
            .where(ExceptionRecord.source_reference.in_(refs))
            .distinct()
            .order_by(ExceptionRecord.case_id)
        ).scalars().all()
    )


def _case_events(session: Session, case_ids: list[str]) -> list[EventRecord]:
    return session.execute(
        select(EventRecord)
        .join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
        .join(ExceptionRecord, ExceptionRecord.id == ExceptionEvidence.exception_id)
        .where(ExceptionRecord.case_id.in_(case_ids))
        .order_by(EventRecord.occurred_at, EventRecord.id)
    ).scalars().unique().all()


def test_one_exception_remains_ungrouped_and_unknown(phase5_session):
    generated = _generate_api_failures(phase5_session, 1)
    case_ids = _cases_for_payments(phase5_session, generated)
    result = IncidentCorrelationService(phase5_session).run(case_ids=case_ids)

    assert result["groups_created"] == 0
    assert result["ungrouped_cases"] == 1
    assert phase5_session.query(Incident).count() == 0
    unknown = phase5_session.query(IncidentCorrelationHistory).filter_by(outcome="UNKNOWN").all()
    assert any(row.case_ids == case_ids for row in unknown)


def test_distinct_exceptions_for_one_payment_create_suspected_incident_only(phase5_session):
    generated = SimulatorScenarioService(phase5_session).generate_scenario(
        "conflicting_system_records", seed=uuid4().hex[:8]
    )
    payment = phase5_session.execute(
        select(SyntheticPayment).where(SyntheticPayment.payment_id == generated["payment_id"])
    ).scalar_one()
    log = phase5_session.execute(
        select(SyntheticTechnologyLog).where(SyntheticTechnologyLog.payment_id == payment.id)
    ).scalar_one()
    log.status_code = 504
    log.latency_ms = 60_000
    log.error_type = "timeout"
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    ExceptionDetectionService(phase5_session).run()
    exceptions = phase5_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.source_reference == generated["payment_id"])
    ).scalars().all()
    assert {exception.exception_type for exception in exceptions} >= {
        "CONFLICTING_SYSTEM_RECORDS",
        "API_PROCESSING_FAILURE",
    }
    for exception in exceptions:
        ClassificationService(phase5_session).evaluate(exception.id)
    case_ids = sorted(exception.case_id for exception in exceptions)
    original_states = {
        case.id: case.status
        for case in phase5_session.execute(select(Case).where(Case.id.in_(case_ids))).scalars()
    }

    result = IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    links = phase5_session.query(CaseIncident).filter_by(incident_id=incident.id, removed_at=None).all()
    history = phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id).one()
    evidence_ids = {item["event_record_id"] for item in history.evidence_references}
    actual_ids = {event.id for event in phase5_session.execute(select(EventRecord).where(
        EventRecord.entity_reference == generated["payment_id"]
    )).scalars()}

    assert result["groups_created"] == 1
    assert incident.status == "SUSPECTED"
    assert {link.case_id for link in links} == set(case_ids)
    assert evidence_ids and evidence_ids <= actual_ids
    assert history.shared_features and all(feature["strength"] == "STRONG" for feature in history.shared_features)
    assert {
        case.id: case.status
        for case in phase5_session.execute(select(Case).where(Case.id.in_(case_ids))).scalars()
    } == original_states


def test_similar_api_errors_with_distinct_incident_identifiers_are_rejected(phase5_session):
    generated = _generate_api_failures(phase5_session, 2)
    case_ids = _cases_for_payments(phase5_session, generated)
    result = IncidentCorrelationService(phase5_session).run(case_ids=case_ids)

    assert result["groups_created"] == 0
    assert phase5_session.query(Incident).count() == 0
    rejected = phase5_session.query(IncidentCorrelationHistory).filter_by(outcome="REJECTED").all()
    assert any("incompatible_incident_identifiers" in str(row.contradictions) for row in rejected)


def test_exact_incident_identifier_correlates_across_time_windows(phase5_session):
    generated = _generate_api_failures(
        phase5_session,
        2,
        incident_identifier="shared-upstream-maintenance-42",
        first_event_age=timedelta(days=2),
    )
    case_ids = _cases_for_payments(phase5_session, generated)
    result = IncidentCorrelationService(
        phase5_session, event_time_window=timedelta(minutes=5)
    ).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()

    assert result["groups_created"] == 1
    assert set(IncidentCorrelationService(phase5_session)._active_case_ids(incident.id)) == set(case_ids)
    summary = IncidentCorrelationService(phase5_session).incident_summary(incident.id)
    first = datetime.fromisoformat(summary["relevant_timestamps"]["first_event_at"])
    last = datetime.fromisoformat(summary["relevant_timestamps"]["last_event_at"])
    assert last - first > timedelta(minutes=5)


def test_duplicate_delivery_is_not_an_incident_group(phase5_session):
    SimulatorScenarioService(phase5_session).generate_scenario("duplicate_event", seed=uuid4().hex[:8])
    ingestion = EventIngestionService(phase5_session)
    first = ingestion.ingest_synthetic()
    repeated = ingestion.ingest_synthetic()
    ExceptionDetectionService(phase5_session).run()
    exception = phase5_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.exception_type == "DUPLICATE_EVENT")
    ).scalar_one()
    ClassificationService(phase5_session).evaluate(exception.id)
    result = IncidentCorrelationService(phase5_session).run(case_ids=[exception.case_id])

    assert repeated["duplicates"] == first["inserted"]
    assert result["groups_created"] == 0
    assert phase5_session.query(Incident).count() == 0
    assert phase5_session.query(ExceptionRecord).filter_by(detection_key=exception.detection_key).count() == 1


def test_late_case_with_exact_identifier_joins_existing_suspected_incident(phase5_session):
    incident_identifier = "delayed-shared-dependency-7"
    earlier = _generate_api_failures(
        phase5_session, 1, incident_identifier=incident_identifier, first_event_age=timedelta(days=1)
    )
    earlier_case_ids = _cases_for_payments(phase5_session, earlier)
    first_run = IncidentCorrelationService(phase5_session).run(case_ids=earlier_case_ids)
    assert first_run["groups_created"] == 0

    later = _generate_api_failures(phase5_session, 1, incident_identifier=incident_identifier)
    later_case_ids = _cases_for_payments(phase5_session, later)
    second_run = IncidentCorrelationService(phase5_session).run(case_ids=later_case_ids)

    incident = phase5_session.query(Incident).one()
    assert second_run["memberships_added"] == 2
    assert set(IncidentCorrelationService(phase5_session)._active_case_ids(incident.id)) == set(
        earlier_case_ids + later_case_ids
    )


def test_reclassification_can_disassociate_cases_and_reject_old_suspected_incident(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="identity-before-change")
    case_ids = _cases_for_payments(phase5_session, generated)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    second_payment = phase5_session.execute(
        select(SyntheticPayment).where(SyntheticPayment.payment_id == generated[1]["payment_id"])
    ).scalar_one()
    log = phase5_session.execute(
        select(SyntheticTechnologyLog).where(SyntheticTechnologyLog.payment_id == second_payment.id)
    ).scalar_one()
    log.status_code = 200
    log.latency_ms = 100
    log.error_type = None
    log.response_body = {"incident_identifier": "identity-after-change"}
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    second_exception = phase5_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.source_reference == generated[1]["payment_id"])
    ).scalar_one()
    revised = ClassificationService(phase5_session).evaluate(second_exception.id)
    assert "UNKNOWN_EXCEPTION" in {
        category["category"] for category in revised["assessment"]["classification"]["categories"]
    }

    result = IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    phase5_session.refresh(incident)
    assert result["groups_created"] == 0
    assert incident.status == "REJECTED"
    assert IncidentCorrelationService(phase5_session)._active_case_ids(incident.id) == []
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(
        incident_id=incident.id, outcome="RECLASSIFIED_UNGROUPED"
    ).count() >= 1


def test_unrelated_simultaneous_failures_do_not_share_an_incident(phase5_session):
    api_generated = _generate_api_failures(phase5_session, 1)
    ledger = SimulatorScenarioService(phase5_session).generate_scenario("ledger_reconciliation_mismatch", seed=uuid4().hex[:8])
    EventIngestionService(phase5_session).ingest_synthetic()
    ExceptionDetectionService(phase5_session).run()
    cases = phase5_session.execute(
        select(ExceptionRecord.case_id).where(
            ExceptionRecord.source_reference.in_([api_generated[0]["payment_id"], ledger["payment_id"]])
        )
    ).scalars().all()
    for exception in phase5_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.case_id.in_(cases))
    ).scalars().all():
        if not phase5_session.query(AssessmentHistory).filter_by(exception_id=exception.id).first():
            ClassificationService(phase5_session).evaluate(exception.id)
    IncidentCorrelationService(phase5_session).run(case_ids=cases)

    api_case = phase5_session.execute(
        select(ExceptionRecord.case_id).where(ExceptionRecord.source_reference == api_generated[0]["payment_id"])
    ).first()[0]
    assert phase5_session.query(CaseIncident).filter_by(case_id=api_case, removed_at=None).count() == 0


def test_repeated_correlation_is_idempotent(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="repeated-correlation")
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(phase5_session)
    first = service.run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    before_history = phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id).count()
    before_links = phase5_session.query(CaseIncident).filter_by(incident_id=incident.id, removed_at=None).count()
    second = service.run(case_ids=case_ids)

    assert first["groups_created"] == 1
    assert second["groups_created"] == 0 and second["memberships_added"] == 0
    assert phase5_session.query(Incident).count() == 1
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id).count() == before_history
    assert phase5_session.query(CaseIncident).filter_by(incident_id=incident.id, removed_at=None).count() == before_links


def test_concurrent_correlation_has_one_incident_and_active_membership_set(phase5_session, postgres_engine):
    generated = _generate_api_failures(phase5_session, 3, incident_identifier="concurrent-correlation")
    case_ids = _cases_for_payments(phase5_session, generated)

    def correlate():
        with Session(postgres_engine) as session:
            return IncidentCorrelationService(session).run(case_ids=case_ids)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: correlate(), range(2)))

    assert sum(result["groups_created"] for result in results) == 1
    assert phase5_session.query(Incident).count() == 1
    incident = phase5_session.query(Incident).one()
    assert set(IncidentCorrelationService(phase5_session)._active_case_ids(incident.id)) == set(case_ids)
    assert phase5_session.query(CaseIncident).filter_by(incident_id=incident.id, removed_at=None).count() == 3


def test_incident_requires_evidence_to_confirm_and_does_not_change_cases(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="confirm-with-evidence")
    case_ids = _cases_for_payments(phase5_session, generated)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    service = IncidentCorrelationService(phase5_session)
    with pytest.raises(ValueError, match="invalid_incident_transition"):
        service.transition_status(incident.id, "CONFIRMED", "Confirm by similarity only")
    service.transition_status(incident.id, "INVESTIGATING", "Begin investigation")
    with pytest.raises(ValueError, match="confirmation_requires_incident_source_evidence"):
        service.transition_status(incident.id, "CONFIRMED", "Confirm by similarity only")
    history = phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id).all()
    evidence_ids = {
        reference["event_record_id"]
        for row in history
        for feature in row.shared_features or []
        if feature.get("strength") == "STRONG"
        for reference in row.evidence_references or []
    }
    states_before = {
        case.id: case.status
        for case in phase5_session.execute(select(Case).where(Case.id.in_(case_ids))).scalars()
    }
    service.transition_status(incident.id, "CONFIRMED", "Investigation validated source identity", sorted(evidence_ids))

    phase5_session.refresh(incident)
    assert incident.status == "CONFIRMED"
    assert {
        case.id: case.status
        for case in phase5_session.execute(select(Case).where(Case.id.in_(case_ids))).scalars()
    } == states_before
    assert phase5_session.query(AuditLog).filter_by(entity_id=incident.id, event_type="incident_status_changed").count() == 2


def test_case_membership_can_be_added_and_removed_with_history(phase5_session):
    identifier = "manual-membership-evidence"
    initial = _generate_api_failures(phase5_session, 2, incident_identifier=identifier)
    initial_case_ids = _cases_for_payments(phase5_session, initial)
    IncidentCorrelationService(phase5_session).run(case_ids=initial_case_ids)
    incident = phase5_session.query(Incident).one()
    added = _generate_api_failures(phase5_session, 1, incident_identifier=identifier)
    added_case_ids = _cases_for_payments(phase5_session, added)
    evidence_ids = [event.id for event in _case_events(phase5_session, initial_case_ids + added_case_ids)]
    service = IncidentCorrelationService(phase5_session)

    service.add_case(incident.id, added_case_ids[0], "Late case shares explicit source incident identifier", evidence_ids)
    assert added_case_ids[0] in service._active_case_ids(incident.id)
    service.remove_case(incident.id, added_case_ids[0], "Manual review found separate operational handling")

    assert added_case_ids[0] not in service._active_case_ids(incident.id)
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(
        incident_id=incident.id, operation="CASE_REMOVED"
    ).count() == 1


def test_split_preserves_parent_and_creates_suspected_child_incidents(phase5_session):
    generated = _generate_api_failures(phase5_session, 4, incident_identifier="incorrect-wide-group")
    case_ids = _cases_for_payments(phase5_session, generated)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    groups = [case_ids[:2], case_ids[2:]]

    result = IncidentCorrelationService(phase5_session).split_incident(
        incident.id, groups, "Independent upstream observations require separate investigations"
    )

    phase5_session.refresh(incident)
    assert incident.status == "SPLIT"
    assert len(result["child_incident_ids"]) == 2
    for child_id, expected_cases in zip(result["child_incident_ids"], groups):
        child = phase5_session.get(Incident, child_id)
        assert child.status == "SUSPECTED"
        assert set(IncidentCorrelationService(phase5_session)._active_case_ids(child_id)) == set(expected_cases)
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id, operation="INCIDENT_SPLIT").count() == 1


def test_confirmed_incidents_merge_with_shared_evidence_and_keep_source_history(phase5_session):
    shared_correlation = "shared-upstream-dependency"
    first = _generate_api_failures(phase5_session, 2, incident_identifier="merge-group-a")
    second = _generate_api_failures(phase5_session, 2, incident_identifier="merge-group-b")
    payment_ids = [item["payment_id"] for item in first + second]
    payments = phase5_session.execute(select(SyntheticPayment).where(SyntheticPayment.payment_id.in_(payment_ids))).scalars().all()
    payment_by_id = {payment.payment_id: payment for payment in payments}
    for item in first + second:
        payment = payment_by_id[item["payment_id"]]
        payment.correlation_id = shared_correlation
        log = phase5_session.execute(select(SyntheticTechnologyLog).where(SyntheticTechnologyLog.payment_id == payment.id)).scalar_one()
        log.correlation_id = shared_correlation
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    ExceptionDetectionService(phase5_session).run()
    for exception in phase5_session.execute(select(ExceptionRecord).where(ExceptionRecord.source_reference.in_(payment_ids))).scalars().all():
        ClassificationService(phase5_session).evaluate(exception.id)
    case_ids = _cases_for_payments(phase5_session, first + second)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incidents = phase5_session.execute(select(Incident).order_by(Incident.id)).scalars().all()
    assert len(incidents) == 2
    service = IncidentCorrelationService(phase5_session)
    strong_refs_by_incident = {}
    for incident in incidents:
        links = service._active_case_ids(incident.id)
        assert len(links) == 2
        case_events = _case_events(phase5_session, links)
        service.transition_status(incident.id, "INVESTIGATING", "Validate shared upstream dependency")
        history = phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id).all()
        evidence_ids = {
            reference["event_record_id"]
            for row in history
            for feature in row.shared_features or []
            if feature.get("strength") == "STRONG"
            for reference in row.evidence_references or []
        }
        service.transition_status(incident.id, "CONFIRMED", "Shared upstream event evidence verified", sorted(evidence_ids))
        strong_refs_by_incident[incident.id] = [event.id for event in case_events]

    target, source = incidents
    merge_refs = strong_refs_by_incident[target.id] + strong_refs_by_incident[source.id]
    merged = service.merge_incidents(
        target.id, source.id, "Confirmed common upstream dependency across both incidents", merge_refs
    )
    phase5_session.refresh(source)

    assert source.status == "MERGED" and source.merged_into_id == target.id
    assert set(merged["case_ids"]) == set(case_ids)
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=source.id, operation="INCIDENT_MERGED").count() == 1


def test_incident_api_exposes_summary_and_history_without_scenario_labels(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="incident-api")
    case_ids = _cases_for_payments(phase5_session, generated)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()

    with TestClient(app) as client:
        listing = client.get("/api/v1/incidents")
        detail = client.get(f"/api/v1/incidents/{incident.id}")
        cases = client.get(f"/api/v1/incidents/{incident.id}/cases")
        evidence = client.get(f"/api/v1/incidents/{incident.id}/evidence")
        history = client.get(f"/api/v1/incidents/{incident.id}/history")
        rerun = client.post(f"/api/v1/incidents/{incident.id}/re-evaluate")

    assert listing.status_code == detail.status_code == cases.status_code == evidence.status_code == history.status_code == rerun.status_code == 200
    assert detail.json()["status"] == "SUSPECTED"
    assert len(cases.json()) == 2
    assert evidence.json() and all(item["event_record_id"] for item in evidence.json())
    assert history.json()
    body = str(detail.json()) + str(evidence.json()) + str(history.json())
    assert "root_cause" not in body and "scenario_name" not in body


def test_synthetic_workload_respects_pair_and_batch_bounds(phase5_session, postgres_engine):
    generated = _generate_api_failures(phase5_session, 150)
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(
        phase5_session,
        batch_size=30,
        candidate_limit=50,
        event_limit=500,
        candidate_pair_limit=10,
    )
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    sqlalchemy_event.listen(postgres_engine, "before_cursor_execute", capture)
    try:
        result = service.run(case_ids=case_ids)
    finally:
        sqlalchemy_event.remove(postgres_engine, "before_cursor_execute", capture)
    assert len(statements) < 80
    plan = phase5_session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM event_records WHERE entity_reference = :entity"),
        {"entity": generated[0]["payment_id"]}).scalar_one()
    assert plan[0]["Plan"]["Actual Rows"] > 0
    print({"synthetic_payments": 150, "correlation_sql_statements": len(statements),
           "candidate_cases": result["candidate_cases_examined"], "candidate_pairs": result["candidate_pairs_examined"],
           "lookup_plan": plan[0]})

    assert result["cases_examined"] == 30
    assert result["candidate_cases_examined"] <= 50
    assert result["candidate_pairs_examined"] <= 10
    assert result["candidate_search_truncated"] is True
    assert result["groups_created"] == 0


def test_runtime_ignores_hidden_labels_and_does_not_query_simulator(phase5_session, postgres_engine):
    generated = _generate_api_failures(phase5_session, 2)
    payments = phase5_session.execute(select(SyntheticPayment)).scalars().all()
    for payment in payments:
        payment.incident_key = "hidden-same-root"
        payment.scenario_name = "hidden-poison-label"
        payment.expected_root_cause = "hidden-poison-cause"
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    sqlalchemy_event.listen(postgres_engine, "before_cursor_execute", capture)
    try:
        result = IncidentCorrelationService(phase5_session).run(case_ids=_cases_for_payments(phase5_session, generated))
    finally:
        sqlalchemy_event.remove(postgres_engine, "before_cursor_execute", capture)
    assert result["groups_created"] == 0
    assert not any("sim_" in statement or "ground_truth" in statement for statement in statements)
    assert "hidden-poison" not in str(phase5_session.query(IncidentCorrelationHistory).all())
    assert all("incident_identifier" not in record.payload for record in phase5_session.query(EventRecord).filter_by(source_system="payments"))


def test_weak_similarity_remains_unknown_without_identifiers(phase5_session):
    generated = _generate_api_failures(phase5_session, 2)
    for log in phase5_session.query(SyntheticTechnologyLog):
        log.response_body = {}
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    result = IncidentCorrelationService(phase5_session).run(case_ids=_cases_for_payments(phase5_session, generated))
    assert result["groups_created"] == 0
    assert any("weak_similarity" in str(row.contradictions) for row in phase5_session.query(IncidentCorrelationHistory))


def test_partial_search_does_not_remove_existing_membership(phase5_session):
    generated = _generate_api_failures(phase5_session, 3, incident_identifier="bounded-search")
    case_ids = _cases_for_payments(phase5_session, generated)
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    result = IncidentCorrelationService(phase5_session, candidate_pair_limit=1).run(case_ids=case_ids)
    assert result["candidate_search_truncated"]
    assert set(IncidentCorrelationService(phase5_session)._active_case_ids(incident.id)) == set(case_ids)


def test_new_evidence_appends_history_without_recreating_incident(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="evidence-refresh")
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(phase5_session)
    service.run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    original_detection = {row.id: row.detected_at for row in phase5_session.query(ExceptionRecord)}
    log = phase5_session.query(SyntheticTechnologyLog).first()
    log.latency_ms += 1000
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    result = service.run(case_ids=case_ids)
    assert result["groups_created"] == 0
    assert phase5_session.query(IncidentCorrelationHistory).filter_by(incident_id=incident.id, operation="EVIDENCE_UPDATED").count() == 1
    assert {row.id: row.detected_at for row in phase5_session.query(ExceptionRecord)} == original_detection


def test_out_of_order_old_identifier_does_not_replace_current_evidence(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="current-source-id")
    case_ids = _cases_for_payments(phase5_session, generated)
    source = phase5_session.query(EventRecord).filter_by(source_system="api_gateway").first()
    envelope = dict(event_id=f"late-old-{uuid4().hex}", source_system=source.source_system,
        event_type=source.event_type, entity_reference=source.entity_reference,
        correlation_id=source.correlation_id, source_record_reference=source.source_record_reference,
        schema_version="1.0", occurred_at=source.occurred_at - timedelta(days=2),
        payload={**source.payload, "incident_identifier": "obsolete-id"})
    EventIngestionService(phase5_session).ingest([envelope])
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    assert incident.incident_key.endswith("current-source-id")


def test_incident_does_not_modify_case_authorization_records(phase5_session):
    from app.models.domain import ActionRecord, HumanApproval, Decision
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="authorization-boundary")
    case_ids = _cases_for_payments(phase5_session, generated)
    phase5_session.add(HumanApproval(id=str(uuid4()), case_id=case_ids[0], approver="reviewer", approved=False))
    phase5_session.add(ActionRecord(id=str(uuid4()), case_id=case_ids[0], action_type="PAYMENT", target="synthetic", status="BLOCKED", attempt_count=0))
    phase5_session.commit()
    before = [(row.id, row.approved) for row in phase5_session.query(HumanApproval)]
    IncidentCorrelationService(phase5_session).run(case_ids=case_ids)
    assert [(row.id, row.approved) for row in phase5_session.query(HumanApproval)] == before
    assert phase5_session.query(ActionRecord).one().status == "BLOCKED"
    assert phase5_session.query(ActionRecord).one().attempt_count == 0
    assert phase5_session.query(Decision).count() == 0
    phase5_session.query(ActionRecord).delete()
    phase5_session.query(HumanApproval).delete()
    phase5_session.commit()


def test_split_two_case_incident_can_leave_both_cases_ungrouped(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="wrong-pair")
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(phase5_session)
    service.run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    result = service.split_incident(incident.id, [[case_id] for case_id in case_ids], "Source identifier reused incorrectly")
    assert set(result["ungrouped_case_ids"]) == set(case_ids)
    assert result["child_incident_ids"] == []
    assert phase5_session.query(CaseIncident).filter_by(removed_at=None).count() == 0
    assert phase5_session.query(CaseIncident).count() == 2


def test_late_confirmation_retains_detection_and_exposes_contradiction(phase5_session):
    generated = _generate_api_failures(phase5_session, 2, incident_identifier="late-confirmation-review")
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(phase5_session)
    service.run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    detected = {row.id: row.detected_at for row in phase5_session.query(ExceptionRecord)}
    payment_event = phase5_session.query(EventRecord).filter_by(source_system="payments", entity_reference=generated[0]["payment_id"]).one()
    EventIngestionService(phase5_session).ingest([dict(event_id=f"late-confirmation-{uuid4().hex}",
        source_system="confirmations", event_type="payment_confirmed", entity_reference=payment_event.entity_reference,
        correlation_id=payment_event.correlation_id, occurred_at=datetime.now(timezone.utc),
        schema_version="1.0", source_record_reference=f"confirmation-{uuid4().hex}",
        payload={"confirmation_status": "CONFIRMED"})])
    for exception in phase5_session.query(ExceptionRecord):
        ClassificationService(phase5_session).evaluate(exception.id)
    service.run(case_ids=case_ids)
    summary = service.incident_summary(incident.id)
    assert any(item["kind"] == "classification_conflict" for item in summary["unresolved_contradictions"])
    assert {row.id: row.detected_at for row in phase5_session.query(ExceptionRecord)} == detected
    service.transition_status(incident.id, "INVESTIGATING", "Review late contradiction")
    refs = [event.id for event in _case_events(phase5_session, case_ids)]
    with pytest.raises(ValueError, match="resolution_of_contradictions"):
        service.transition_status(incident.id, "CONFIRMED", "Cannot confirm unresolved contradiction", refs)


def test_manual_removal_is_not_undone_by_automatic_correlation(phase5_session):
    generated = _generate_api_failures(phase5_session, 3, incident_identifier="manual-exclusion")
    case_ids = _cases_for_payments(phase5_session, generated)
    service = IncidentCorrelationService(phase5_session)
    service.run(case_ids=case_ids)
    incident = phase5_session.query(Incident).one()
    service.remove_case(incident.id, case_ids[0], "Identity reused for a separate exception")
    service.run(case_ids=case_ids)
    assert set(service._active_case_ids(incident.id)) == set(case_ids[1:])


def test_distinct_identifiers_are_not_contaminated_by_shared_trace(phase5_session):
    first = _generate_api_failures(phase5_session, 2, incident_identifier="root-a")
    second = _generate_api_failures(phase5_session, 2, incident_identifier="root-b")
    for log in phase5_session.query(SyntheticTechnologyLog):
        log.correlation_id = "one-batch-trace"
    phase5_session.commit()
    EventIngestionService(phase5_session).ingest_synthetic()
    cases = _cases_for_payments(phase5_session, first + second)
    IncidentCorrelationService(phase5_session).run(case_ids=cases)
    assert phase5_session.query(Incident).count() == 2
    for incident in phase5_session.query(Incident):
        assert len(IncidentCorrelationService(phase5_session)._active_case_ids(incident.id)) == 2
