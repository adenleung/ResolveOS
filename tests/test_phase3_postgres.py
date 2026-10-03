from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.adapters import SyntheticSourceAdapters
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import DetectionHistory, EventRecord, ExceptionEvidence, IngestionError
from app.ingestion.service import EventIngestionService
from app.main import app
from app.models.domain import AuditLog, Case, Evidence, ExceptionRecord
from app.simulator.models import SyntheticConfirmationEvent, SyntheticPayment, SyntheticWorkflowState
from app.simulator.service import SimulatorScenarioService


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        pytest.skip("Phase 3 integration tests require PostgreSQL via DATABASE_URL")
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def phase3_session(postgres_engine):
    with Session(postgres_engine) as session:
        session.execute(delete(ExceptionEvidence))
        session.execute(delete(DetectionHistory))
        detected_cases = session.execute(
            select(ExceptionRecord.case_id).where(ExceptionRecord.detection_key.is_not(None))
        ).scalars().all()
        session.execute(delete(Evidence).where(Evidence.case_id.in_(detected_cases)))
        session.execute(delete(AuditLog).where(AuditLog.event_type.in_(["exception_detected", "exception_evidence_updated"])))
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


def _generate(session: Session, scenario: str):
    return SimulatorScenarioService(session).generate_scenario(scenario, seed=uuid4().hex[:8])


def _ingest_and_detect(session: Session, **detection_options):
    ingestion = EventIngestionService(session).ingest_synthetic()
    result = ExceptionDetectionService(session, **detection_options).run()
    return ingestion, result


def test_normal_operations_and_repeated_ingestion_are_idempotent(phase3_session):
    _generate(phase3_session, "normal_success")
    service = EventIngestionService(phase3_session)
    first = service.ingest_synthetic()
    second = service.ingest_synthetic()
    result = ExceptionDetectionService(phase3_session).run()

    assert first["inserted"] > 0
    assert second["inserted"] == 0
    assert second["duplicates"] == first["inserted"]
    assert result["detections_created"] == 0
    assert phase3_session.query(ExceptionRecord).filter(ExceptionRecord.detection_key.is_not(None)).count() == 0
    assert phase3_session.query(EventRecord).filter(EventRecord.processing_status == "PROCESSED").count() == first["inserted"]


def test_actual_ledger_mismatch_creates_exception_case_evidence_and_audit(phase3_session):
    _generate(phase3_session, "ledger_reconciliation_mismatch")
    _ingest_and_detect(phase3_session)

    exception = phase3_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.exception_type == "RECONCILIATION_MISMATCH")
    ).scalar_one()
    case = phase3_session.get(Case, exception.case_id)
    evidence = phase3_session.execute(
        select(EventRecord).join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
        .where(ExceptionEvidence.exception_id == exception.id)
    ).scalars().all()
    assert case is not None and case.status.value == "DETECTED"
    assert {event.source_system for event in evidence} == {"payments", "ledger"}
    assert any(event.payload["amount"] != next(other.payload["amount"] for other in evidence if other.source_system == "payments")
               for event in evidence if event.source_system == "ledger")
    assert phase3_session.query(AuditLog).filter_by(entity_id=exception.id, event_type="exception_detected").count() == 1
    repeated = ExceptionDetectionService(phase3_session).run()
    assert repeated["detections_created"] == 0
    assert phase3_session.query(ExceptionRecord).filter_by(detection_key=exception.detection_key).count() == 1


def test_missing_confirmation_waits_for_window_and_late_event_is_appended(phase3_session):
    generated = _generate(phase3_session, "missing_confirmation")
    payment = phase3_session.execute(
        select(SyntheticPayment).where(SyntheticPayment.payment_id == generated["payment_id"])
    ).scalar_one()
    aged_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    payment.created_at = aged_at
    payment.updated_at = aged_at
    phase3_session.commit()

    EventIngestionService(phase3_session).ingest_synthetic()
    first = ExceptionDetectionService(phase3_session, confirmation_window=timedelta(minutes=5)).run()
    exception = phase3_session.execute(
        select(ExceptionRecord).where(ExceptionRecord.exception_type == "PAYMENT_CONFIRMATION_MISSING")
    ).scalar_one()
    assert first["detections_created"] == 1
    assert exception.detected_at is not None

    payment.status = "SETTLED"
    phase3_session.commit()
    late = SyntheticConfirmationEvent(
        id=f"late-{uuid4().hex}",
        payment_id=payment.id,
        event_id=f"late-event-{uuid4().hex}",
        event_type="payment_confirmed",
        status="CONFIRMED",
        occurred_at=datetime.now(timezone.utc) - timedelta(minutes=8),
        correlation_id=payment.correlation_id,
        is_duplicate=False,
        payload={"delivery": "late"},
    )
    phase3_session.add(late)
    phase3_session.commit()
    EventIngestionService(phase3_session).ingest_synthetic()
    repeated = ExceptionDetectionService(phase3_session, confirmation_window=timedelta(minutes=5)).run()

    phase3_session.refresh(exception)
    assert repeated["detections_created"] == 0
    assert exception.condition_status == "LATE_EVIDENCE_RECEIVED"
    assert phase3_session.query(ExceptionRecord).filter_by(detection_key=exception.detection_key).count() == 1
    assert phase3_session.query(DetectionHistory).filter_by(exception_id=exception.id, event_type="EVIDENCE_ADDED").count() == 1
    evidence_sources = phase3_session.execute(
        select(EventRecord.source_system)
        .join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
        .where(ExceptionEvidence.exception_id == exception.id)
    ).scalars().all()
    assert evidence_sources.count("payments") == 2
    assert evidence_sources.count("confirmations") == 1


def test_delayed_confirmation_inside_window_does_not_create_false_exception(phase3_session):
    _generate(phase3_session, "delayed_event")
    _ingest_and_detect(phase3_session, confirmation_window=timedelta(minutes=5))
    assert phase3_session.query(ExceptionRecord).filter_by(exception_type="PAYMENT_CONFIRMATION_MISSING").count() == 0


def test_confirmation_window_boundary_is_inclusive_at_deadline(phase3_session):
    generated = _generate(phase3_session, "missing_confirmation")
    payment = phase3_session.execute(
        select(SyntheticPayment).where(SyntheticPayment.payment_id == generated["payment_id"])
    ).scalar_one()
    occurred_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    payment.created_at = occurred_at
    payment.updated_at = occurred_at
    phase3_session.commit()
    EventIngestionService(phase3_session).ingest_synthetic()

    window = timedelta(minutes=5)
    before_deadline = ExceptionDetectionService(
        phase3_session,
        confirmation_window=window,
        clock=lambda: occurred_at + window - timedelta(microseconds=1),
    ).run()
    at_deadline = ExceptionDetectionService(
        phase3_session,
        confirmation_window=window,
        clock=lambda: occurred_at + window,
    ).run()

    assert before_deadline["detections_created"] == 0
    assert at_deadline["detections_created"] == 1


def test_duplicate_business_event_is_detected_but_duplicate_delivery_is_not(phase3_session):
    _generate(phase3_session, "duplicate_event")
    service = EventIngestionService(phase3_session)
    first = service.ingest_synthetic()
    second = service.ingest_synthetic()
    result = ExceptionDetectionService(phase3_session).run()

    assert second["duplicates"] == first["inserted"]
    assert result["detections_created"] == 1
    assert phase3_session.query(ExceptionRecord).filter_by(exception_type="DUPLICATE_EVENT").count() == 1
    assert phase3_session.query(ExceptionRecord).filter_by(exception_type="PAYMENT_DUPLICATE").count() == 0


def test_api_failure_conflicting_records_and_overdue_workflow_are_observed(phase3_session):
    _generate(phase3_session, "api_timeout")
    conflict = _generate(phase3_session, "conflicting_system_records")
    _generate(phase3_session, "normal_success")
    workflow = phase3_session.execute(
        select(SyntheticWorkflowState).where(SyntheticWorkflowState.workflow_id == conflict["workflow_id"])
    ).scalar_one()
    workflow.last_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    phase3_session.commit()

    _ingest_and_detect(phase3_session, workflow_deadline=timedelta(minutes=30))
    types = {row[0] for row in phase3_session.execute(select(ExceptionRecord.exception_type)).all()}
    assert "API_PROCESSING_FAILURE" in types
    assert "CONFLICTING_SYSTEM_RECORDS" in types
    assert "WORKFLOW_EXCEPTION" in types


def test_completed_workflow_snapshot_supersedes_stale_incomplete_snapshot(phase3_session):
    generated = _generate(phase3_session, "missing_confirmation")
    workflow = phase3_session.execute(
        select(SyntheticWorkflowState).where(SyntheticWorkflowState.workflow_id == generated["workflow_id"])
    ).scalar_one()
    workflow.last_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    phase3_session.commit()
    EventIngestionService(phase3_session).ingest_synthetic()

    workflow.workflow_status = "APPROVED"
    workflow.last_updated_at = datetime.now(timezone.utc)
    phase3_session.commit()
    EventIngestionService(phase3_session).ingest_synthetic()
    ExceptionDetectionService(phase3_session, workflow_deadline=timedelta(minutes=30)).run()

    assert phase3_session.query(ExceptionRecord).filter_by(exception_type="WORKFLOW_EXCEPTION").count() == 0


def test_out_of_order_and_invalid_events_are_durable_and_reported(phase3_session):
    _generate(phase3_session, "normal_success")
    events = SyntheticSourceAdapters().collect(phase3_session)
    ingestion = EventIngestionService(phase3_session)
    result = ingestion.ingest(reversed(events))
    invalid = ingestion.ingest([{"source_system": "test", "event_id": "missing-required-fields"}])
    detection = ExceptionDetectionService(phase3_session).run()

    assert result["inserted"] == len(events)
    assert invalid["rejected"] == 1
    assert detection["events_processed"] == len(events)
    assert ingestion.status()["unresolved_ingestion_errors"] == 1
    assert phase3_session.query(ExceptionRecord).filter(ExceptionRecord.detection_key.is_not(None)).count() == 0


def test_database_failure_rolls_back_current_event_and_allows_retry(phase3_session):
    valid = {
        "event_id": "durable-before-failure",
        "source_system": "test",
        "event_type": "test.recorded",
        "entity_reference": "entity-1",
        "occurred_at": datetime.now(timezone.utc),
        "schema_version": "1.0",
        "source_record_reference": "source-1",
        "payload": {"value": "persisted"},
    }
    invalid_json = {**valid, "event_id": "invalid-json", "payload": {"value": object()}}
    result = EventIngestionService(phase3_session).ingest([valid, invalid_json])

    assert result["inserted"] == 1
    assert result["rejected"] == 1
    assert phase3_session.query(EventRecord).filter_by(event_id=valid["event_id"]).count() == 1
    assert phase3_session.query(EventRecord).filter_by(event_id=invalid_json["event_id"]).count() == 0
    assert phase3_session.query(IngestionError).filter(IngestionError.error_message.like("persistence_failed:%")).count() == 1
    retry = EventIngestionService(phase3_session).ingest([{**invalid_json, "payload": {"value": "retry"}}])
    assert retry["inserted"] == 1


def test_interrupted_batch_keeps_committed_events_available_for_reprocessing(phase3_session):
    event = {
        "event_id": "committed-before-interruption",
        "source_system": "test",
        "event_type": "test.recorded",
        "entity_reference": "entity-1",
        "occurred_at": datetime.now(timezone.utc),
        "schema_version": "1.0",
        "source_record_reference": "source-1",
        "payload": {"value": "durable"},
    }

    def interrupted_batch():
        yield event
        raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        EventIngestionService(phase3_session).ingest(interrupted_batch())
    assert phase3_session.query(EventRecord).filter_by(event_id=event["event_id"]).count() == 1
    retry = EventIngestionService(phase3_session).ingest([event])
    assert retry["inserted"] == 0 and retry["duplicates"] == 1


def test_detection_is_safe_when_run_concurrently_and_db_keys_are_unique(phase3_session, postgres_engine):
    _generate(phase3_session, "ledger_reconciliation_mismatch")
    EventIngestionService(phase3_session).ingest_synthetic()

    def detect_once():
        with Session(postgres_engine) as session:
            return ExceptionDetectionService(session).run()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: detect_once(), range(2)))

    detection_types = [
        row[0]
        for row in phase3_session.execute(select(ExceptionRecord.exception_type)).all()
    ]
    assert "RECONCILIATION_MISMATCH" in detection_types
    assert len(detection_types) == len(set(detection_types))
    assert sum(result["detections_created"] for result in results) == len(detection_types)
    event = phase3_session.query(EventRecord).first()
    phase3_session.add(
        EventRecord(
            id=f"duplicate-row-{uuid4().hex}",
            event_id=event.event_id,
            source_system=event.source_system,
            event_type=event.event_type,
            entity_reference=event.entity_reference,
            occurred_at=event.occurred_at,
            ingested_at=datetime.now(timezone.utc),
            schema_version="1.0",
            source_record_reference=event.source_record_reference,
            payload=event.payload,
            processing_status="PENDING",
            processing_attempts=0,
            duplicate_receipts=0,
        )
    )
    with pytest.raises(IntegrityError):
        phase3_session.commit()
    phase3_session.rollback()


def test_versioned_ingestion_detection_and_exception_apis_hide_scenario_labels(phase3_session):
    _generate(phase3_session, "ledger_reconciliation_mismatch")
    with TestClient(app) as client:
        ingestion = client.post("/api/v1/ingestion/synthetic")
        detection = client.post("/api/v1/detection/run")
        listing = client.get("/api/v1/exceptions")
        stats = client.get("/api/v1/detection/stats")

        assert ingestion.status_code == 200
        assert ingestion.json()["inserted"] > 0
        assert detection.status_code == 200
        assert listing.status_code == 200
        assert stats.status_code == 200
        exception = next(item for item in listing.json() if item["exception_type"] == "RECONCILIATION_MISMATCH")
        detail = client.get(f"/api/v1/exceptions/{exception['id']}")
        assert detail.status_code == 200
        payload = detail.json()
        assert {item["source_system"] for item in payload["evidence"]} == {"payments", "ledger"}
        assert all("scenario" not in item["payload"] and "root_cause" not in item["payload"] for item in payload["evidence"])
        assert "unresolved_ingestion_errors" in client.get("/api/v1/ingestion/status").json()