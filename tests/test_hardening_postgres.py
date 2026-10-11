"""Real PostgreSQL evidence integrity and temporal memory regressions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_phase11_postgres import session, settings, publish, new_case, WORK_ACCESS
from test_phase6_postgres import postgres_engine
from app.ingestion.service import EventIngestionService
from app.ingestion.models import EventRecord, IngestionError
from app.memory.service import MemoryService
from app.memory.models import MemoryRetrieval, MemoryVersion
from test_phase10_postgres import queued, claim, execute
from app.models.domain import VerificationResult, Case


def envelope(session):
    now = session.scalar(select(func.clock_timestamp()))
    return dict(event_id="hardening-receipt", source_system="payments", event_type="payment.recorded",
        entity_reference="synthetic-only", source_record_reference="synthetic-only", occurred_at=now,
        schema_version="1.0", payload={"payment_status": "SETTLED"})


@pytest.mark.parametrize("field,value", [("payload", {"payment_status": "FAILED"}),
    ("entity_reference", "different-case"), ("source_record_reference", "different-source"),
    ("event_type", "different-event"), ("schema_version", "2.0")])
def test_conflicting_replay_does_not_replace_evidence(session, field, value):
    record = envelope(session)
    assert EventIngestionService(session).ingest([record])["inserted"] == 1
    result = EventIngestionService(session).ingest([{**record, field: value}])
    assert result["rejected"] == 1 and result["duplicates"] == 0
    stored = session.scalar(select(EventRecord))
    assert stored.payload == record["payload"] and stored.duplicate_receipts == 0
    assert session.scalar(select(IngestionError.error_message)) == "event_identity_content_conflict"


def test_concurrent_retries_count_every_receipt(session, postgres_engine):
    record = envelope(session)
    EventIngestionService(session).ingest([record])
    barrier = Barrier(6)
    def retry(_):
        with Session(postgres_engine) as connection:
            barrier.wait(timeout=20)
            return EventIngestionService(connection).ingest([record])
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(retry, range(6)))
    assert all(row["duplicates"] == 1 for row in results)
    session.expire_all()
    assert session.scalar(select(EventRecord.duplicate_receipts)) == 6
    assert session.scalar(select(func.count()).select_from(EventRecord)) == 1


def test_changed_json_scalar_type_is_a_conflicting_replay(session):
    record = envelope(session)
    record["payload"]["numeric_flag"] = 1
    EventIngestionService(session).ingest([record])
    altered = {**record, "payload": {**record["payload"], "numeric_flag": True}}
    assert EventIngestionService(session).ingest([altered])["rejected"] == 1


def test_memory_review_after_snapshot_is_not_retrievable(session, settings):
    _, _, memory = publish(session, settings)
    target = new_case(session)
    version = session.get(MemoryVersion, memory["id"])
    cutoff = version.reviewed_at - timedelta(microseconds=1)
    result = MemoryService(session, settings).retrieve(target.id, version.category, WORK_ACCESS, as_of=cutoff)
    session.commit()
    assert result["memories"] == []
    assert session.scalar(select(MemoryRetrieval)).limits["information_window"] == cutoff.isoformat()
    current = MemoryService(session, settings).retrieve(target.id, version.category, WORK_ACCESS)
    assert current["memories"][0]["id"] == version.id


@pytest.mark.parametrize("invalid", ["naive", "future"])
def test_memory_invalid_snapshot_fails_closed(session, settings, invalid):
    target = new_case(session)
    now = session.scalar(select(func.clock_timestamp()))
    cutoff = now.replace(tzinfo=None) if invalid == "naive" else now + timedelta(days=1)
    with pytest.raises(ValueError, match="memory_information_window_invalid"):
        MemoryService(session, settings).retrieve(target.id, "PAYMENT_CONFIRMATION_MISMATCH", WORK_ACCESS, as_of=cutoff)


def test_changed_ledger_balance_cannot_be_verified_resolved(session, settings):
    parts, authorization, submitted, database = queued(session, settings)
    execute(database, settings, claim(session, settings))
    parts[5].balance_after = -1
    session.commit()
    result = execute(database, settings, claim(session, settings))
    assert result["outcome"] == "FAILED_VERIFICATION"
    assert "monetary_source_changed" in result["discrepancies"]
    session.expire_all()
    assert session.get(Case, parts[0].id).status.value == "ESCALATED"
    assert session.scalar(select(VerificationResult.success)) is False
