from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.classification.models import AssessmentHistory
from app.classification.priority import PriorityEngine, recommend_routing
from app.classification.service import ClassificationService
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import DetectionHistory, EventRecord, ExceptionEvidence, IngestionError
from app.ingestion.service import EventIngestionService
from app.main import app
from app.models.domain import AuditLog, Case, Evidence, ExceptionRecord
from app.simulator.models import SyntheticPayment, SyntheticWorkflowState
from app.simulator.service import SimulatorScenarioService


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        pytest.skip("Phase 4 integration tests require PostgreSQL via DATABASE_URL")
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def phase4_session(postgres_engine):
    with Session(postgres_engine) as session:
        session.execute(delete(AssessmentHistory))
        session.execute(delete(ExceptionEvidence))
        session.execute(delete(DetectionHistory))
        detected_cases = session.execute(
            select(ExceptionRecord.case_id).where(ExceptionRecord.detection_key.is_not(None))
        ).scalars().all()
        session.execute(delete(Evidence).where(Evidence.case_id.in_(detected_cases)))
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
                    ]
                )
            )
        )
        session.execute(delete(ExceptionRecord).where(ExceptionRecord.detection_key.is_not(None)))
        session.execute(delete(Case).where(Case.id.in_(detected_cases)))
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


def _create_exception(session: Session, scenario: str, exception_type: str) -> ExceptionRecord:
    source_scenario = "normal_success" if scenario == "workflow_overdue" else scenario
    generated = SimulatorScenarioService(session).generate_scenario(source_scenario, seed=uuid4().hex[:8])
    now = datetime.now(timezone.utc)
    if scenario == "missing_confirmation":
        payment = session.execute(
            select(SyntheticPayment).where(SyntheticPayment.payment_id == generated["payment_id"])
        ).scalar_one()
        old = now - timedelta(minutes=10)
        payment.created_at = old
        payment.updated_at = old
    elif scenario == "workflow_overdue":
        workflow = session.execute(
            select(SyntheticWorkflowState).where(SyntheticWorkflowState.workflow_id == generated["workflow_id"])
        ).scalar_one()
        workflow.workflow_status = "PROCESSING"
        workflow.last_updated_at = now - timedelta(hours=1)
    session.commit()
    EventIngestionService(session).ingest_synthetic()
    ExceptionDetectionService(session).run()
    return session.execute(
        select(ExceptionRecord).where(ExceptionRecord.exception_type == exception_type)
    ).scalar_one()


def _unknown_exception(session: Session) -> ExceptionRecord:
    suffix = uuid4().hex
    case_id = f"phase4-case-{suffix}"
    exception = ExceptionRecord(
        id=f"phase4-exception-{suffix}",
        case_id=case_id,
        exception_type="UNMAPPED_LEGACY_TYPE",
        description="Synthetic unsupported condition for classification validation.",
        severity="MEDIUM",
        source_reference=f"unknown-entity-{suffix}",
        detection_key=f"phase4-unknown-{suffix}",
        detected_at=datetime.now(timezone.utc),
        condition_status="OPEN",
    )
    session.add(
        Case(
            id=case_id,
            case_number=f"CASE-PHASE4-{suffix.upper()}",
            external_ref=exception.source_reference,
            summary=exception.description,
            priority="MEDIUM",
        )
    )
    session.add(exception)
    session.commit()
    return exception


@pytest.mark.parametrize(
    ("scenario", "exception_type", "expected_category"),
    [
        ("missing_confirmation", "PAYMENT_CONFIRMATION_MISSING", "PAYMENT_CONFIRMATION_MISMATCH"),
        ("ledger_reconciliation_mismatch", "RECONCILIATION_MISMATCH", "RECONCILIATION_MISMATCH"),
        ("api_timeout", "API_PROCESSING_FAILURE", "API_PROCESSING_FAILURE"),
        ("workflow_overdue", "WORKFLOW_EXCEPTION", "WORKFLOW_EXCEPTION"),
        ("conflicting_system_records", "CONFLICTING_SYSTEM_RECORDS", "CONFLICTING_RECORDS"),
        ("duplicate_event", "DUPLICATE_EVENT", "DUPLICATE_EVENT"),
    ],
)
def test_supported_exception_families_classify_from_synthetic_records(
    phase4_session, scenario, exception_type, expected_category
):
    exception = _create_exception(phase4_session, scenario, exception_type)
    result = ClassificationService(phase4_session).evaluate(exception.id)
    categories = result["assessment"]["classification"]["categories"]

    assert expected_category in {category["category"] for category in categories}
    assert all(category["rule_version"] == "classification-rules-1.0" for category in categories)
    assert result["assessment"]["classification"]["classification_timestamp"].endswith("+00:00")
    assert result["assessment"]["classification"]["supporting_evidence_references"]


def test_normal_simulated_records_do_not_create_an_exception_or_supported_category(phase4_session):
    SimulatorScenarioService(phase4_session).generate_scenario("normal_success", seed=91001)
    EventIngestionService(phase4_session).ingest_synthetic()
    result = ExceptionDetectionService(phase4_session).run()
    assert result["detections_created"] == 0
    assert phase4_session.query(ExceptionRecord).count() == 0


def test_reconciliation_can_have_multiple_categories_without_collapsing_conflict(phase4_session):
    exception = _create_exception(phase4_session, "ledger_reconciliation_mismatch", "RECONCILIATION_MISMATCH")
    assessment = ClassificationService(phase4_session).evaluate(exception.id)["assessment"]
    categories = {item["category"] for item in assessment["classification"]["categories"]}

    assert {"RECONCILIATION_MISMATCH", "CONFLICTING_RECORDS"} <= categories
    assert "conflicting_evidence" in assessment["classification"]["uncertainty_flags"]
    assert assessment["classification"]["operational_eligible"] is False


def test_replayed_confirmation_does_not_imply_duplicate_monetary_effect(phase4_session):
    exception = _create_exception(phase4_session, "duplicate_event", "DUPLICATE_EVENT")
    assessment = ClassificationService(phase4_session).evaluate(exception.id)["assessment"]

    assert assessment["priority"]["input_facts"]["potential_duplicate_monetary_effect"] is False
    assert "RISK" not in assessment["routing"]["recommended_specialists"]


def test_duplicate_effect_risk_and_document_routing_require_their_own_evidence():
    now = datetime.now(timezone.utc)

    def payment_event(record_id: str, entity: str) -> EventRecord:
        return EventRecord(
            id=record_id,
            event_id=record_id,
            source_system="payments",
            event_type="payment.recorded",
            entity_reference=entity,
            occurred_at=now,
            ingested_at=now,
            schema_version="1.0",
            source_record_reference=entity,
            payload={"payment_status": "PENDING", "amount": "100.00", "currency": "SGD", "idempotency_key": "shared-key"},
        )

    current = payment_event("payment-one-event", "payment-one")
    second = payment_event("payment-two-event", "payment-two")
    priority = PriorityEngine().calculate(
        [{"category": "DUPLICATE_EVENT"}],
        [current],
        [current, second],
        now,
        now,
        True,
    )
    routing = recommend_routing(
        [{"category": "DOCUMENT_STATUS_EXCEPTION"}],
        [],
        [],
    )

    assert priority["input_facts"]["potential_duplicate_monetary_effect"] is True
    assert {reference["entity_reference"] for reference in priority["input_facts"]["potential_duplicate_payment_evidence"]} == {
        "payment-one",
        "payment-two",
    }
    assert priority["level"] == "CRITICAL"
    assert routing["recommended_specialists"] == ["DOCUMENT", "COMPLIANCE"]


def test_unknown_and_missing_evidence_route_to_human_triage(phase4_session):
    exception = _unknown_exception(phase4_session)
    assessment = ClassificationService(phase4_session).evaluate(exception.id)["assessment"]

    assert assessment["classification"]["categories"][0]["category"] == "UNKNOWN_EXCEPTION"
    assert {"unsupported_condition", "missing_evidence"} <= set(assessment["classification"]["uncertainty_flags"])
    assert assessment["classification"]["operational_eligible"] is False
    assert assessment["routing"]["fallback_queue"] == "HUMAN_TRIAGE"
    assert assessment["routing"]["human_triage_required"] is True


def test_specialist_routing_uses_multiple_categories_and_payment_context(phase4_session):
    recon = _create_exception(phase4_session, "ledger_reconciliation_mismatch", "RECONCILIATION_MISMATCH")
    recon_assessment = ClassificationService(phase4_session).evaluate(recon.id)["assessment"]
    assert {"TRANSACTION", "RISK"} <= set(recon_assessment["routing"]["recommended_specialists"])

    missing = _create_exception(phase4_session, "missing_confirmation", "PAYMENT_CONFIRMATION_MISSING")
    missing_assessment = ClassificationService(phase4_session).evaluate(missing.id)["assessment"]
    assert {"TRANSACTION", "TECHNOLOGY"} <= set(missing_assessment["routing"]["recommended_specialists"])


def test_classification_references_are_real_source_records_and_repeat_is_idempotent(phase4_session):
    exception = _create_exception(phase4_session, "api_timeout", "API_PROCESSING_FAILURE")
    service = ClassificationService(phase4_session)
    first = service.evaluate(exception.id)
    audit_count = phase4_session.query(AuditLog).filter_by(entity_id=exception.id).count()
    second = service.evaluate(exception.id, reason="manual rerun")
    history = service.get_history(exception.id)
    refs = first["assessment"]["classification"]["supporting_evidence_references"]
    existing_ids = set(phase4_session.execute(select(EventRecord.id)).scalars().all())

    assert first["changed"] is True
    assert second["changed"] is False
    assert len(history) == 1
    assert phase4_session.query(AuditLog).filter_by(entity_id=exception.id).count() == audit_count
    assert {reference["event_record_id"] for reference in refs} <= existing_ids


def test_late_payment_source_record_revises_routing_and_preserves_history(phase4_session):
    generated = SimulatorScenarioService(phase4_session).generate_scenario("api_timeout", seed=uuid4().hex[:8])
    source_events = EventIngestionService(phase4_session).adapters.collect(phase4_session)
    api_events = [event for event in source_events if event["source_system"] == "api_gateway"]
    EventIngestionService(phase4_session).ingest(api_events)
    ExceptionDetectionService(phase4_session).run()
    exception = phase4_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.exception_type == "API_PROCESSING_FAILURE")
    ).scalar_one()
    service = ClassificationService(phase4_session)
    initial = service.evaluate(exception.id)
    assert initial["assessment"]["routing"]["recommended_specialists"] == ["TECHNOLOGY"]

    payment_events = [event for event in source_events if event["source_system"] == "payments"]
    EventIngestionService(phase4_session).ingest(payment_events)
    revised = service.evaluate(exception.id, reason="Payment source record arrived late")

    assert revised["changed"] is True
    assert revised["assessment"]["routing"]["recommended_specialists"] == ["TRANSACTION", "TECHNOLOGY"]
    assert revised["assessment"]["change_reasons"]
    assert generated["payment_id"] in {
        reference["entity_reference"]
        for reference in revised["assessment"]["classification"]["supporting_evidence_references"]
    }
    assert len(service.get_history(exception.id)) == 2
    assert generated["payment_id"] in {event.entity_reference for event in phase4_session.query(EventRecord).all()}


def test_priority_escalates_and_deescalates_without_resetting_sla_start(phase4_session):
    exception = _create_exception(phase4_session, "api_timeout", "API_PROCESSING_FAILURE")
    payment = phase4_session.execute(
        select(SyntheticPayment).where(SyntheticPayment.payment_id == exception.source_reference)
    ).scalar_one()
    service = ClassificationService(phase4_session)
    initial = service.evaluate(exception.id)
    initial_level = initial["assessment"]["priority"]["level"]
    sla_start = datetime.fromisoformat(initial["assessment"]["sla"]["started_at"])
    original_amount = payment.amount

    payment.amount = Decimal("6000.00")
    phase4_session.commit()
    EventIngestionService(phase4_session).ingest_synthetic()
    escalated = service.evaluate(exception.id)
    assert escalated["assessment"]["change_context"]["previous_values"]["priority"] == initial_level

    payment.amount = original_amount
    phase4_session.commit()
    EventIngestionService(phase4_session).ingest_synthetic()
    deescalated = service.evaluate(exception.id)

    assert initial_level == "HIGH"
    assert escalated["assessment"]["priority"]["level"] == "CRITICAL"
    assert escalated["assessment"]["priority"]["action_authorization"] == "NOT_EVALUATED"
    assert deescalated["assessment"]["priority"]["level"] == initial_level
    assert datetime.fromisoformat(deescalated["assessment"]["sla"]["started_at"]) == sla_start
    assert datetime.fromisoformat(deescalated["assessment"]["sla"]["deadline"]) == sla_start + timedelta(hours=4)
    case = phase4_session.get(Case, exception.case_id)
    assert case.priority == initial_level
    assert phase4_session.query(AssessmentHistory).filter_by(exception_id=exception.id).count() == 3


def test_sla_remaining_and_overdue_boundary_are_timezone_aware(phase4_session):
    exception = _unknown_exception(phase4_session)
    current = [datetime.now(timezone.utc)]
    service = ClassificationService(phase4_session, clock=lambda: current[0])
    assessed = service.evaluate(exception.id)
    deadline = datetime.fromisoformat(assessed["assessment"]["sla"]["deadline"])

    current[0] = deadline
    at_deadline = service.get_exception_assessment(exception.id)["sla"]
    current[0] = deadline + timedelta(microseconds=1)
    after_deadline = service.get_exception_assessment(exception.id)["sla"]

    assert at_deadline["remaining_seconds"] == 0
    assert at_deadline["overdue"] is False
    assert after_deadline["overdue"] is True
    assert datetime.fromisoformat(at_deadline["deadline"]).tzinfo is not None


def test_concurrent_assessment_writes_one_initial_history_revision(phase4_session, postgres_engine):
    exception = _create_exception(phase4_session, "api_timeout", "API_PROCESSING_FAILURE")
    exception_id = exception.id

    def evaluate_once():
        with Session(postgres_engine) as session:
            return ClassificationService(session).evaluate(exception_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: evaluate_once(), range(2)))

    assert sum(result["changed"] for result in results) == 1
    assert phase4_session.query(AssessmentHistory).filter_by(exception_id=exception_id).count() == 1
    assert phase4_session.query(AuditLog).filter_by(entity_id=exception_id, event_type="exception_classified").count() == 1


def test_versioned_classification_priority_and_routing_apis(phase4_session):
    exception = _create_exception(phase4_session, "api_timeout", "API_PROCESSING_FAILURE")
    with TestClient(app) as client:
        classified = client.post(
            f"/api/v1/exceptions/{exception.id}/classify",
            json={"reason": "Phase 4 API verification"},
        )
        classification = client.get(f"/api/v1/exceptions/{exception.id}/classification")
        priority = client.get(f"/api/v1/cases/{exception.case_id}/priority")
        routing = client.get(f"/api/v1/cases/{exception.case_id}/routing")
        repeated = client.post(f"/api/v1/exceptions/{exception.id}/classify/re-evaluate")

    assert classified.status_code == 200 and classified.json()["changed"] is True
    assert classification.status_code == 200 and len(classification.json()["history"]) == 1
    assert priority.status_code == 200
    assert priority.json()["priority"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert priority.json()["sla"]["deadline"]
    assert routing.status_code == 200
    assert {"TECHNOLOGY", "TRANSACTION"} <= set(routing.json()["recommended_specialists"])
    assert repeated.status_code == 200 and repeated.json()["changed"] is False
    response_text = str(classification.json())
    assert "scenario_name" not in response_text
    assert "root_cause" not in response_text
