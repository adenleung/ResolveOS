from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.simulator.models import (
    SyntheticConfirmationEvent,
    SyntheticLedgerEntry,
    SyntheticPayment,
    SyntheticTechnologyLog,
    SyntheticWorkflowState,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SourceAdapter(Protocol):
    source_system: str

    def collect(self, session: Session) -> list[dict[str, Any]]: ...


class PaymentAdapter:
    source_system = "payments"

    def collect(self, session: Session) -> list[dict[str, Any]]:
        rows = session.execute(select(SyntheticPayment).order_by(SyntheticPayment.created_at)).scalars()
        return [
            {
                "event_id": f"payment:{row.id}:{row.updated_at.isoformat()}",
                "source_system": self.source_system,
                "event_type": "payment.recorded",
                "entity_reference": row.payment_id,
                "correlation_id": row.correlation_id,
                "occurred_at": _utc(row.updated_at),
                "schema_version": "1.0",
                "source_record_reference": row.payment_id,
                "payload": {
                    "payment_status": row.status,
                    "amount": str(row.amount),
                    "currency": row.currency,
                    "idempotency_key": row.idempotency_key,
                    "beneficiary": row.beneficiary,
                },
            }
            for row in rows
        ]


class LedgerAdapter:
    source_system = "ledger"

    def collect(self, session: Session) -> list[dict[str, Any]]:
        rows = session.execute(select(SyntheticLedgerEntry).order_by(SyntheticLedgerEntry.created_at)).scalars()
        return [
            {
                "event_id": f"ledger:{row.id}:{row.updated_at.isoformat()}",
                "source_system": self.source_system,
                "event_type": "ledger.entry_recorded",
                "entity_reference": row.payment.payment_id,
                "correlation_id": row.payment.correlation_id,
                "occurred_at": _utc(row.created_at),
                "schema_version": "1.0",
                "source_record_reference": row.ledger_transaction_id,
                "payload": {
                    "entry_type": row.entry_type,
                    "amount": str(row.amount),
                    "currency": row.currency,
                    "balance_after": str(row.balance_after),
                    "ledger_status": row.status,
                    "ledger_transaction_id": row.ledger_transaction_id,
                },
            }
            for row in rows
        ]


class ConfirmationAdapter:
    source_system = "confirmations"

    def collect(self, session: Session) -> list[dict[str, Any]]:
        rows = session.execute(select(SyntheticConfirmationEvent).order_by(SyntheticConfirmationEvent.occurred_at)).scalars()
        return [
            {
                "event_id": row.event_id,
                "source_system": self.source_system,
                "event_type": row.event_type,
                "entity_reference": row.payment.payment_id,
                "correlation_id": row.correlation_id,
                "occurred_at": _utc(row.occurred_at),
                "schema_version": "1.0",
                "source_record_reference": row.event_id,
                "payload": {
                    "confirmation_status": row.status,
                    "is_duplicate": row.is_duplicate,
                },
            }
            for row in rows
        ]


class ApiFailureAdapter:
    source_system = "api_gateway"

    def collect(self, session: Session) -> list[dict[str, Any]]:
        rows = session.execute(select(SyntheticTechnologyLog).order_by(SyntheticTechnologyLog.occurred_at)).scalars()
        return [
            {
                "event_id": f"api:{row.id}:{row.updated_at.isoformat()}",
                "source_system": self.source_system,
                "event_type": "api.request_completed",
                "entity_reference": row.payment.payment_id if row.payment is not None else row.correlation_id,
                "correlation_id": row.correlation_id,
                "occurred_at": _utc(row.occurred_at),
                "schema_version": "1.0",
                "source_record_reference": row.id,
                "payload": {
                    "service_name": row.service_name,
                    "method": row.method,
                    "endpoint": row.endpoint,
                    "status_code": row.status_code,
                    "latency_ms": row.latency_ms,
                    "error_type": row.error_type,
                    "incident_identifier": (row.response_body or {}).get("incident_identifier"),
                    "dependency_failure_id": (row.response_body or {}).get("dependency_failure_id"),
                },
            }
            for row in rows
        ]


class WorkflowAdapter:
    source_system = "workflow"

    def collect(self, session: Session) -> list[dict[str, Any]]:
        rows = session.execute(select(SyntheticWorkflowState).order_by(SyntheticWorkflowState.last_updated_at)).scalars()
        return [
            {
                "event_id": f"workflow:{row.id}:{row.updated_at.isoformat()}",
                "source_system": self.source_system,
                "event_type": "workflow.state_changed",
                "entity_reference": row.payment.payment_id,
                "correlation_id": row.payment.correlation_id,
                "occurred_at": _utc(row.last_updated_at),
                "schema_version": "1.0",
                "source_record_reference": row.workflow_id,
                "payload": {
                    "workflow_status": row.workflow_status,
                    "current_step": row.current_step,
                    "pending_tasks": row.pending_tasks or [],
                    "approval_required": row.approval_required,
                    "approval_status": row.approval_status,
                },
            }
            for row in rows
        ]


class SyntheticSourceAdapters:
    def __init__(self, adapters: list[SourceAdapter] | None = None):
        self.adapters = adapters or [
            PaymentAdapter(),
            LedgerAdapter(),
            ConfirmationAdapter(),
            ApiFailureAdapter(),
            WorkflowAdapter(),
        ]

    def collect(self, session: Session) -> list[dict[str, Any]]:
        return [event for adapter in self.adapters for event in adapter.collect(session)]
