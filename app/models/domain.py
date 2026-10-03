from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.domain.case_service import CaseLifecycleService, CaseState
from app.models.base import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Case(Base, TimestampMixin):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, index=True)
    case_number = Column(String, unique=True, nullable=False, index=True)
    external_ref = Column(String, nullable=True)
    status = Column(Enum(CaseState, name="case_status"), default=CaseState.DETECTED, nullable=False)
    summary = Column(Text, nullable=True)
    priority = Column(String, default="MEDIUM", nullable=False)
    sla_started_at = Column(DateTime(timezone=True), nullable=True)
    sla_deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    sla_rule_version = Column(String, nullable=True)
    orchestration_generation = Column(Integer, nullable=False, default=0, server_default="0")
    orchestration_fingerprint = Column(String, nullable=True)

    exceptions = relationship("ExceptionRecord", back_populates="case")
    incidents = relationship("CaseIncident", back_populates="case")
    evidence = relationship("Evidence", back_populates="case")
    findings = relationship("InvestigatorFinding", back_populates="case")
    decisions = relationship("Decision", back_populates="case")
    actions = relationship("ActionRecord", back_populates="case")
    approvals = relationship("HumanApproval", back_populates="case")
    verifications = relationship("VerificationResult", back_populates="case")
    audit_events = relationship("AuditLog", back_populates="case")

    def transition_to(self, new_state: CaseState) -> CaseState:
        service = CaseLifecycleService()
        self.status = service.transition(self.status, new_state)
        return self.status


class ExceptionRecord(Base, TimestampMixin):
    __tablename__ = "exceptions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    exception_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, nullable=False, default="MEDIUM")
    source_reference = Column(String, nullable=True)
    detection_key = Column(String, nullable=True, unique=True, index=True)
    detected_at = Column(DateTime(timezone=True), nullable=True)
    condition_status = Column(String, nullable=False, default="OPEN")

    case = relationship("Case", back_populates="exceptions")


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, index=True)
    incident_key = Column(String, unique=True, index=True, nullable=False)
    incident_type = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="MEDIUM")
    description = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="SUSPECTED")
    correlation_rule_version = Column(String, nullable=True)
    merged_into_id = Column(String, ForeignKey("incidents.id"), nullable=True)

    cases = relationship("CaseIncident", back_populates="incident")


class CaseIncident(Base, TimestampMixin):
    __tablename__ = "case_incidents"
    __table_args__ = (
        Index(
            "uq_case_incidents_active_case",
            "case_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
            sqlite_where=text("removed_at IS NULL"),
        ),
        Index(
            "ix_case_incidents_active_incident",
            "incident_id",
            postgresql_where=text("removed_at IS NULL"),
            sqlite_where=text("removed_at IS NULL"),
        ),
    )

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=False)
    relationship_type = Column(String, nullable=False, default="RELATED")
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removal_reason = Column(Text, nullable=True)
    correlation_history_id = Column(String, ForeignKey("incident_correlation_history.id"), nullable=True)

    case = relationship("Case", back_populates="incidents")
    incident = relationship("Incident", back_populates="cases")


class Evidence(Base, TimestampMixin):
    __tablename__ = "evidence"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    relevant_event_timestamp = Column(DateTime(timezone=True), nullable=True)
    retrieval_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    payload = Column(JSON, nullable=False)
    integrity_metadata = Column(JSON, nullable=True)

    case = relationship("Case", back_populates="evidence")


class InvestigatorFinding(Base, TimestampMixin):
    __tablename__ = "investigator_findings"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    investigator_name = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    confidence = Column(String, nullable=False, default="MEDIUM")
    evidence_refs = Column(JSON, default=list)

    case = relationship("Case", back_populates="findings")


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    decision_type = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    rationale = Column(Text, nullable=True)
    effective = Column(Boolean, default=True, nullable=False)

    case = relationship("Case", back_populates="decisions")


class ActionRecord(Base, TimestampMixin):
    __tablename__ = "actions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False)
    target = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    payload = Column(JSON, nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)

    case = relationship("Case", back_populates="actions")


class HumanApproval(Base, TimestampMixin):
    __tablename__ = "human_approvals"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    approver = Column(String, nullable=False)
    approved = Column(Boolean, nullable=False)
    rationale = Column(Text, nullable=True)

    case = relationship("Case", back_populates="approvals")


class VerificationResult(Base, TimestampMixin):
    __tablename__ = "verification_results"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    action_id = Column(String, ForeignKey("actions.id"), nullable=True)
    verification_type = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    observed_state = Column(JSON, nullable=True)
    detail = Column(Text, nullable=True)

    case = relationship("Case", back_populates="verifications")


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    active_version = Column(String, nullable=True)


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id = Column(String, primary_key=True, index=True)
    policy_id = Column(String, ForeignKey("policies.id"), nullable=False)
    version = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=True, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    details = Column(JSON, default=dict)

    case = relationship("Case", back_populates="audit_events")
