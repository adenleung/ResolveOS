"""Read-only feature extraction against actual existing PostgreSQL contracts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import pytest
from test_phase6_postgres import postgres_engine
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import Case, ExceptionRecord, ActionRecord, HumanApproval, AuditLog
from app.ml.snapshot import intake_snapshot


def seed(session):
    now = datetime.now(timezone.utc)
    case = Case(id=str(uuid4()), case_number=str(uuid4()), created_at=now - timedelta(minutes=1))
    session.add(case)
    session.flush()
    exception = ExceptionRecord(id=str(uuid4()), case_id=case.id, exception_type="API_PROCESSING_FAILURE",
        description="synthetic timeout", detected_at=now - timedelta(seconds=5))
    session.add(exception)
    session.flush()
    event = EventRecord(id=str(uuid4()), event_id=str(uuid4()), source_system="api_gateway", event_type="api.request",
        entity_reference="synthetic", source_record_reference="synthetic", schema_version="1.0",
        occurred_at=now - timedelta(seconds=10), ingested_at=now - timedelta(seconds=9),
        payload={"status_code": 504, "latency_ms": 31000, "error_type": "timeout"})
    session.add(event)
    session.flush()
    link = ExceptionEvidence(id=str(uuid4()), exception_id=exception.id, event_record_id=event.id,
        linked_at=now - timedelta(seconds=4))
    session.add(link)
    session.flush()
    return now, exception, link, event


def test_real_snapshot_and_no_writes(postgres_engine):
    with Session(postgres_engine) as session:
        now, exception, _, _ = seed(session)
        before = [session.scalar(select(func.count()).select_from(model)) for model in (ActionRecord, HumanApproval, AuditLog)]
        result = intake_snapshot(session, exception.id, now)
        assert result["features"]["api_failure_count"] == 1
        assert result["baseline"] == "API_PROCESSING_FAILURE"
        assert result["action_authorization"] == "NOT_EVALUATED"
        assert before == [session.scalar(select(func.count()).select_from(model)) for model in (ActionRecord, HumanApproval, AuditLog)]
        assert result == intake_snapshot(session, exception.id, now)


def test_late_evidence_link_excluded(postgres_engine):
    with Session(postgres_engine) as session:
        now, exception, link, _ = seed(session)
        link.linked_at = now + timedelta(seconds=1)
        session.flush()
        result = intake_snapshot(session, exception.id, now)
        assert result["features"]["evidence_available"] == 0
        assert result["baseline"] == "UNKNOWN_EXCEPTION"


def test_future_ingestion_excluded(postgres_engine):
    with Session(postgres_engine) as session:
        now, exception, _, event = seed(session)
        event.ingested_at = now + timedelta(seconds=1)
        session.flush()
        assert intake_snapshot(session, exception.id, now)["features"]["evidence_available"] == 0


def test_unknown_or_not_yet_detected_exception(postgres_engine):
    with Session(postgres_engine) as session:
        now, exception, _, _ = seed(session)
        for identifier, cutoff in (("missing", now), (exception.id, now - timedelta(minutes=1))):
            with pytest.raises(ValueError):
                intake_snapshot(session, identifier, cutoff)
