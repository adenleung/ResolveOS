from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ingestion.adapters import SyntheticSourceAdapters
from app.ingestion.models import EventRecord, IngestionError
from app.ingestion.schemas import EventEnvelope


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {"unserializable_payload": repr(value)}


class EventIngestionService:
    def __init__(self, session: Session, adapters: SyntheticSourceAdapters | None = None):
        self.session = session
        self.adapters = adapters or SyntheticSourceAdapters()

    def ingest_synthetic(self) -> dict[str, Any]:
        return self.ingest(self.adapters.collect(self.session))

    def ingest(self, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        stats: dict[str, Any] = {"received": 0, "inserted": 0, "duplicates": 0, "rejected": 0, "errors": []}
        for raw in records:
            stats["received"] += 1
            try:
                event = EventEnvelope.model_validate(raw)
            except ValidationError as exc:
                stats["rejected"] += 1
                error = IngestionError(
                    id=str(uuid4()),
                    source_system=str(raw.get("source_system", "unknown"))[:100],
                    source_record_reference=str(raw.get("source_record_reference", ""))[:255] or None,
                    raw_payload=_json_safe(raw),
                    error_message=exc.json(),
                )
                self.session.add(error)
                self.session.commit()
                stats["errors"].append({"source_record_reference": error.source_record_reference, "message": "schema_validation_failed"})
                continue

            existing = self.session.execute(
                select(EventRecord).where(
                    EventRecord.source_system == event.source_system,
                    EventRecord.event_id == event.event_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.duplicate_receipts += 1
                stats["duplicates"] += 1
                self.session.commit()
                continue

            row = EventRecord(
                id=str(uuid4()),
                event_id=event.event_id,
                source_system=event.source_system,
                event_type=event.event_type,
                entity_reference=event.entity_reference,
                correlation_id=event.correlation_id,
                occurred_at=event.occurred_at,
                ingested_at=_now(),
                schema_version=event.schema_version,
                source_record_reference=event.source_record_reference,
                payload=event.payload,
                processing_status="PENDING",
                processing_attempts=0,
                duplicate_receipts=0,
            )
            self.session.add(row)
            try:
                self.session.commit()
                stats["inserted"] += 1
            except IntegrityError:
                self.session.rollback()
                raced = self.session.execute(
                    select(EventRecord).where(
                        EventRecord.source_system == event.source_system,
                        EventRecord.event_id == event.event_id,
                    )
                ).scalar_one_or_none()
                if raced is None:
                    raise
                raced.duplicate_receipts += 1
                self.session.commit()
                stats["duplicates"] += 1
            except Exception as exc:
                self.session.rollback()
                error = IngestionError(
                    id=str(uuid4()),
                    source_system=event.source_system,
                    source_record_reference=event.source_record_reference,
                    raw_payload=_json_safe(raw),
                    error_message=f"persistence_failed: {type(exc).__name__}: {exc}",
                )
                self.session.add(error)
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise exc
                stats["rejected"] += 1
                stats["errors"].append(
                    {"source_record_reference": event.source_record_reference, "message": "persistence_failed"}
                )
        return stats

    def status(self) -> dict[str, Any]:
        counts = self.session.execute(
            select(EventRecord.processing_status, func.count()).group_by(EventRecord.processing_status)
        ).all()
        by_status = {status: count for status, count in counts}
        return {
            "stored_events": sum(by_status.values()),
            "pending": by_status.get("PENDING", 0),
            "processed": by_status.get("PROCESSED", 0),
            "failed": by_status.get("FAILED", 0),
            "unresolved_ingestion_errors": self.session.execute(
                select(func.count()).select_from(IngestionError).where(IngestionError.resolved.is_(False))
            ).scalar_one(),
        }