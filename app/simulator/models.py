from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class SyntheticPayment(Base, TimestampMixin):
    __tablename__ = "sim_payments"

    id = Column(String, primary_key=True)
    payment_id = Column(String, unique=True, nullable=False, index=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    amount = Column(Numeric(precision=18, scale=2), nullable=False)
    currency = Column(String, nullable=False, default="SGD")
    beneficiary = Column(String, nullable=False)
    status = Column(String, nullable=False, default="INITIATED")
    correlation_id = Column(String, nullable=False, index=True)
    incident_key = Column(String, nullable=True, index=True)
    scenario_name = Column(String, nullable=False, index=True)
    processing_outcome = Column(String, nullable=True)
    expected_root_cause = Column(String, nullable=True)

    ledger_entries = relationship("SyntheticLedgerEntry", back_populates="payment")
    confirmations = relationship("SyntheticConfirmationEvent", back_populates="payment")
    technology_logs = relationship("SyntheticTechnologyLog", back_populates="payment")
    workflow_states = relationship("SyntheticWorkflowState", back_populates="payment")


class SyntheticLedgerEntry(Base, TimestampMixin):
    __tablename__ = "sim_ledger_entries"

    id = Column(String, primary_key=True)
    payment_id = Column(String, ForeignKey("sim_payments.id"), nullable=False, index=True)
    ledger_transaction_id = Column(String, unique=True, nullable=False, index=True)
    entry_type = Column(String, nullable=False)
    amount = Column(Numeric(precision=18, scale=2), nullable=False)
    currency = Column(String, nullable=False, default="SGD")
    balance_after = Column(Numeric(precision=18, scale=2), nullable=False)
    source_system = Column(String, nullable=False, default="ledger")
    status = Column(String, nullable=False, default="POSTED")
    description = Column(Text, nullable=True)

    payment = relationship("SyntheticPayment", back_populates="ledger_entries")


class SyntheticConfirmationEvent(Base, TimestampMixin):
    __tablename__ = "sim_confirmation_events"

    id = Column(String, primary_key=True)
    payment_id = Column(String, ForeignKey("sim_payments.id"), nullable=False, index=True)
    event_id = Column(String, unique=True, nullable=False, index=True)
    event_type = Column(String, nullable=False, default="payment_confirmed")
    status = Column(String, nullable=False, default="CONFIRMED")
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    correlation_id = Column(String, nullable=False, index=True)
    is_duplicate = Column(Boolean, nullable=False, default=False)
    payload = Column(JSON, nullable=True)

    payment = relationship("SyntheticPayment", back_populates="confirmations")


class SyntheticTechnologyLog(Base, TimestampMixin):
    __tablename__ = "sim_technology_logs"

    id = Column(String, primary_key=True)
    payment_id = Column(String, ForeignKey("sim_payments.id"), nullable=True, index=True)
    service_name = Column(String, nullable=False, index=True)
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    correlation_id = Column(String, nullable=False, index=True)
    error_type = Column(String, nullable=True)
    response_body = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)

    payment = relationship("SyntheticPayment", back_populates="technology_logs")


class SyntheticWorkflowState(Base, TimestampMixin):
    __tablename__ = "sim_workflow_states"

    id = Column(String, primary_key=True)
    payment_id = Column(String, ForeignKey("sim_payments.id"), nullable=False, index=True)
    workflow_id = Column(String, unique=True, nullable=False, index=True)
    workflow_status = Column(String, nullable=False, default="PENDING")
    current_step = Column(String, nullable=False)
    pending_tasks = Column(JSON, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=False)
    approval_status = Column(String, nullable=False, default="NOT_REQUESTED")
    last_updated_at = Column(DateTime(timezone=True), nullable=False)

    payment = relationship("SyntheticPayment", back_populates="workflow_states")


class SyntheticPolicy(Base, TimestampMixin):
    __tablename__ = "sim_policies"

    id = Column(String, primary_key=True)
    policy_code = Column(String, unique=True, nullable=False, index=True)
    version = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    rule_payload = Column(JSON, nullable=False)
