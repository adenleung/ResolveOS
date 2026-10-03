from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, Index

from app.models.base import Base


class IncidentCorrelationRun(Base):
    __tablename__ = "incident_correlation_runs"

    id = Column(String, primary_key=True)
    rule_version = Column(String, nullable=False)
    status = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cases_examined = Column(Integer, nullable=False)
    candidate_pairs_examined = Column(Integer, nullable=False)
    groups_created = Column(Integer, nullable=False)
    memberships_added = Column(Integer, nullable=False)
    ungrouped_cases = Column(Integer, nullable=False)
    settings = Column(JSON, nullable=False)


class IncidentCorrelationHistory(Base):
    __tablename__ = "incident_correlation_history"
    __table_args__ = (
        Index("ix_incident_correlation_history_incident_id", "incident_id"),
        Index("ix_incident_correlation_history_run_id", "correlation_run_id"),
        Index("ix_incident_correlation_history_created_at", "created_at"),
    )

    id = Column(String, primary_key=True)
    correlation_run_id = Column(String, ForeignKey("incident_correlation_runs.id"), nullable=True)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=True)
    operation = Column(String, nullable=False)
    outcome = Column(String, nullable=False)
    correlation_key = Column(String, nullable=True)
    rule_version = Column(String, nullable=False)
    case_ids = Column(JSON, nullable=False)
    shared_features = Column(JSON, nullable=False)
    evidence_references = Column(JSON, nullable=False)
    contradictions = Column(JSON, nullable=False)
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))