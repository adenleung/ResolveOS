from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.models.base import Base


class EventRecord(Base):
    __tablename__ = "event_records"
    __table_args__ = (UniqueConstraint("source_system", "event_id", name="uq_event_source_event_id"),)

    id = Column(String, primary_key=True)
    event_id = Column(String, nullable=False)
    source_system = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    entity_reference = Column(String, nullable=False, index=True)
    correlation_id = Column(String, nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    schema_version = Column(String, nullable=False)
    source_record_reference = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    processing_status = Column(String, nullable=False, default="PENDING", index=True)
    processing_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    duplicate_receipts = Column(Integer, nullable=False, default=0)


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id = Column(String, primary_key=True)
    source_system = Column(String, nullable=False, index=True)
    source_record_reference = Column(String, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved = Column(Boolean, nullable=False, default=False)


class ExceptionEvidence(Base):
    __tablename__ = "exception_evidence"
    __table_args__ = (UniqueConstraint("exception_id", "event_record_id", name="uq_exception_event_evidence"),)

    id = Column(String, primary_key=True)
    exception_id = Column(String, ForeignKey("exceptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_record_id = Column(String, ForeignKey("event_records.id"), nullable=False, index=True)
    linked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DetectionHistory(Base):
    __tablename__ = "detection_history"

    id = Column(String, primary_key=True)
    exception_id = Column(String, ForeignKey("exceptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    event_occurred_at = Column(DateTime(timezone=True), nullable=True)
    details = Column(JSON, nullable=False, default=dict)