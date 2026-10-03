from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.simulator.models import (
    SyntheticConfirmationEvent,
    SyntheticLedgerEntry,
    SyntheticPayment,
    SyntheticPolicy,
    SyntheticTechnologyLog,
    SyntheticWorkflowState,
)


SCENARIO_DEFINITIONS: dict[str, dict[str, Any]] = {
    "normal_success": {
        "seed": 101,
        "status": "SETTLED",
        "processing_outcome": "completed",
        "root_cause": "none",
        "confirmation_status": "CONFIRMED",
        "workflow_status": "APPROVED",
        "approval_required": False,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "missing_confirmation": {
        "seed": 202,
        "status": "PENDING",
        "processing_outcome": "pending_confirmation",
        "root_cause": "missing_confirmation_event",
        "confirmation_status": "MISSING",
        "workflow_status": "AWAITING_CONFIRMATION",
        "approval_required": False,
        "missing_confirmation": True,
        "duplicate_event": False,
    },
    "payment_status_mismatch": {
        "seed": 303,
        "status": "PENDING",
        "processing_outcome": "status_mismatch",
        "root_cause": "payment_status_mismatch",
        "confirmation_status": "CONFIRMED",
        "workflow_status": "PROCESSING",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "ledger_reconciliation_mismatch": {
        "seed": 404,
        "status": "HOLD",
        "processing_outcome": "reconciliation_mismatch",
        "root_cause": "ledger_balance_discrepancy",
        "confirmation_status": "CONFIRMED",
        "workflow_status": "RECONCILING",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
        "ledger_amount_delta": "10.00",
    },
    "api_timeout": {
        "seed": 505,
        "status": "TIMEOUT",
        "processing_outcome": "api_timeout",
        "root_cause": "technology_timeout",
        "confirmation_status": "DELAYED",
        "workflow_status": "WAITING_FOR_RETRY",
        "approval_required": False,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "duplicate_event": {
        "seed": 606,
        "status": "RETRY",
        "processing_outcome": "duplicate_event_detected",
        "root_cause": "duplicate_confirmation",
        "confirmation_status": "REPLAYED",
        "workflow_status": "REVIEW_REQUIRED",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": True,
    },
    "duplicate_payment_risk": {
        "seed": 707,
        "status": "HOLD",
        "processing_outcome": "duplicate_payment_risk",
        "root_cause": "duplicate_idempotency_risk",
        "confirmation_status": "PENDING",
        "workflow_status": "REVIEW_REQUIRED",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "delayed_event": {
        "seed": 808,
        "status": "PENDING",
        "processing_outcome": "delayed_confirmation",
        "root_cause": "late_event_arrival",
        "confirmation_status": "DELAYED",
        "workflow_status": "WAITING_FOR_LATE_EVENT",
        "approval_required": False,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "partial_processing_failure": {
        "seed": 909,
        "status": "FAILED",
        "processing_outcome": "partial_failure",
        "root_cause": "partial_processing_failure",
        "confirmation_status": "MISSING",
        "workflow_status": "FAILED",
        "approval_required": True,
        "missing_confirmation": True,
        "duplicate_event": False,
    },
    "conflicting_system_records": {
        "seed": 1001,
        "status": "INVESTIGATING",
        "processing_outcome": "conflicting_records",
        "root_cause": "conflicting_source_records",
        "confirmation_status": "CONFLICTING",
        "workflow_status": "INVESTIGATING",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "missing_document": {
        "seed": 1102,
        "status": "HOLD",
        "processing_outcome": "document_missing",
        "root_cause": "missing_document",
        "confirmation_status": "PENDING",
        "workflow_status": "DOCUMENT_REQUIRED",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "shared_incident_multiple_exceptions": {
        "seed": 1203,
        "status": "INVESTIGATING",
        "processing_outcome": "multi_exception_shared_incident",
        "root_cause": "shared_incident_root_cause",
        "confirmation_status": "CONFIRMED",
        "workflow_status": "INVESTIGATING",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
    "similar_look_but_different_causes": {
        "seed": 1304,
        "status": "HOLD",
        "processing_outcome": "similar_look_different_causes",
        "root_cause": "misleading_similarity",
        "confirmation_status": "CONFIRMED",
        "workflow_status": "REVIEW_REQUIRED",
        "approval_required": True,
        "missing_confirmation": False,
        "duplicate_event": False,
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SimulatorScenarioService:
    def __init__(self, session: Session):
        self.session = session

    def list_scenarios(self) -> list[str]:
        return sorted(SCENARIO_DEFINITIONS)

    def generate_scenario(self, scenario_name: str, seed: int | None = None) -> dict[str, Any]:
        if scenario_name not in SCENARIO_DEFINITIONS:
            raise ValueError(f"Unsupported scenario: {scenario_name}")

        config = SCENARIO_DEFINITIONS[scenario_name]
        rng = random.Random(seed if seed is not None else config["seed"])
        now = _utc_now()

        payment_id = f"sim-payment-{scenario_name}-{seed if seed is not None else config['seed']}"
        idempotency_key = f"idem-{scenario_name}-{seed if seed is not None else config['seed']}"
        correlation_id = f"corr-{scenario_name}-{seed if seed is not None else config['seed']}"
        workflow_id = f"wf-{scenario_name}-{seed if seed is not None else config['seed']}"
        incident_key = f"incident-{scenario_name}-{seed if seed is not None else config['seed']}"
        ledger_transaction_id = f"lt-{scenario_name}-{seed if seed is not None else config['seed']}"

        existing = self.session.execute(
            select(SyntheticPayment).where(SyntheticPayment.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "scenario_name": existing.scenario_name,
                "payment_id": existing.payment_id,
                "idempotency_key": existing.idempotency_key,
                "correlation_id": existing.correlation_id,
                "incident_key": existing.incident_key,
                "status": existing.status,
                "amount": str(existing.amount),
                "currency": existing.currency,
                "beneficiary": existing.beneficiary,
                "workflow_id": self.session.execute(
                    select(SyntheticWorkflowState.workflow_id).where(SyntheticWorkflowState.payment_id == existing.id)
                ).scalar_one_or_none(),
                "root_cause": existing.expected_root_cause,
            }

        payment = SyntheticPayment(
            id=payment_id,
            payment_id=payment_id,
            idempotency_key=idempotency_key,
            amount=Decimal(str(1000 + rng.randint(0, 4000) / 10)),
            currency="SGD",
            beneficiary=f"beneficiary-{rng.randint(10, 99)}",
            status=config["status"],
            correlation_id=correlation_id,
            incident_key=incident_key,
            scenario_name=scenario_name,
            processing_outcome=config["processing_outcome"],
            expected_root_cause=config["root_cause"],
        )
        self.session.add(payment)
        self.session.flush()

        ledger_balance = Decimal("5000.00")
        if config["status"] in {"SETTLED", "HOLD"}:
            ledger_balance = Decimal("5100.00")
        if config["status"] in {"PENDING", "TIMEOUT", "FAILED", "INVESTIGATING"}:
            ledger_balance = Decimal("4900.00")

        ledger_entry = SyntheticLedgerEntry(
            id=f"ledger-{payment_id}",
            payment_id=payment.id,
            ledger_transaction_id=ledger_transaction_id,
            entry_type="DEBIT" if scenario_name.startswith("normal") or config["status"] in {"SETTLED", "HOLD"} else "HOLD",
            amount=payment.amount + Decimal(config.get("ledger_amount_delta", "0.00")),
            currency=payment.currency,
            balance_after=ledger_balance,
            source_system="ledger",
            status="POSTED" if config["status"] != "HOLD" else "PENDING",
            description=f"Generated ledger record for {scenario_name}",
        )
        self.session.add(ledger_entry)

        if config["missing_confirmation"]:
            confirmation_count = 0
        else:
            confirmation_count = 1 + (1 if config["duplicate_event"] else 0)

        for index in range(confirmation_count):
            event_id = f"confirmation-{payment_id}-{index}"
            self.session.add(
                SyntheticConfirmationEvent(
                    id=event_id,
                    payment_id=payment.id,
                    event_id=event_id,
                    event_type="payment_confirmed",
                    status=config["confirmation_status"],
                    occurred_at=now + timedelta(minutes=index + 1),
                    correlation_id=correlation_id,
                    is_duplicate=index > 0,
                    payload={"scenario": scenario_name, "duplicate": index > 0},
                )
            )

        self.session.add(
            SyntheticTechnologyLog(
                id=f"tech-{payment_id}",
                payment_id=payment.id,
                service_name="payment-gateway",
                method="POST",
                endpoint="/payments",
                status_code=200 if config["processing_outcome"] not in {"api_timeout", "partial_failure"} else 504,
                latency_ms=120 if config["processing_outcome"] not in {"api_timeout"} else 60000,
                correlation_id=correlation_id,
                error_type=None if config["processing_outcome"] not in {"api_timeout"} else "timeout",
                response_body={"status": config["status"]},
                occurred_at=now,
            )
        )

        self.session.add(
            SyntheticWorkflowState(
                id=f"workflow-{payment_id}",
                payment_id=payment.id,
                workflow_id=workflow_id,
                workflow_status=config["workflow_status"],
                current_step="confirm_payment" if config["status"] in {"SETTLED", "PENDING"} else "review",
                pending_tasks=["approve" if config["approval_required"] else "monitor"],
                approval_required=config["approval_required"],
                approval_status="APPROVED" if config["workflow_status"] == "APPROVED" else "PENDING",
                last_updated_at=now,
            )
        )

        policy_seed = seed if seed is not None else config["seed"]
        policy = SyntheticPolicy(
            id=f"policy-{scenario_name}-{policy_seed}",
            policy_code=f"POL-{scenario_name.upper()}-{policy_seed}",
            version="1.0",
            name=f"{scenario_name.replace('_', ' ').title()} Policy",
            description="Synthetic policy used for simulator validation.",
            approval_required=config["approval_required"],
            effective_from=now - timedelta(days=30),
            effective_to=None,
            rule_payload={
                "scenario": scenario_name,
                "requires_approval": config["approval_required"],
                "status": config["status"],
            },
        )
        self.session.add(policy)
        self.session.commit()

        return {
            "scenario_name": scenario_name,
            "payment_id": payment.payment_id,
            "idempotency_key": payment.idempotency_key,
            "correlation_id": payment.correlation_id,
            "incident_key": payment.incident_key,
            "status": payment.status,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "beneficiary": payment.beneficiary,
            "workflow_id": workflow_id,
            "root_cause": payment.expected_root_cause,
        }

    def get_payment(self, payment_id: str) -> SyntheticPayment | None:
        return self.session.execute(select(SyntheticPayment).where(SyntheticPayment.payment_id == payment_id)).scalar_one_or_none()

    def get_ledger_records(self, payment_id: str):
        payment = self.get_payment(payment_id)
        if payment is None:
            return []
        return self.session.execute(
            select(SyntheticLedgerEntry).where(SyntheticLedgerEntry.payment_id == payment.id).order_by(SyntheticLedgerEntry.created_at.asc())
        ).scalars().all()

    def get_confirmations(self, payment_id: str):
        payment = self.get_payment(payment_id)
        if payment is None:
            return []
        return self.session.execute(
            select(SyntheticConfirmationEvent).where(SyntheticConfirmationEvent.payment_id == payment.id).order_by(SyntheticConfirmationEvent.occurred_at.asc())
        ).scalars().all()

    def get_logs(self, correlation_id: str | None = None, payment_id: str | None = None):
        query = select(SyntheticTechnologyLog)
        if payment_id is not None:
            payment = self.get_payment(payment_id)
            if payment is None:
                return []
            query = query.where(SyntheticTechnologyLog.payment_id == payment.id)
        if correlation_id is not None:
            query = query.where(SyntheticTechnologyLog.correlation_id == correlation_id)
        query = query.order_by(SyntheticTechnologyLog.occurred_at.asc())
        return self.session.execute(query).scalars().all()

    def get_workflow(self, workflow_id: str):
        return self.session.execute(select(SyntheticWorkflowState).where(SyntheticWorkflowState.workflow_id == workflow_id)).scalar_one_or_none()

    def get_policies(self):
        return self.session.execute(select(SyntheticPolicy).order_by(SyntheticPolicy.effective_from.asc())).scalars().all()

    def reset_state(self) -> None:
        self.session.execute(text("DELETE FROM sim_technology_logs"))
        self.session.execute(text("DELETE FROM sim_confirmation_events"))
        self.session.execute(text("DELETE FROM sim_ledger_entries"))
        self.session.execute(text("DELETE FROM sim_workflow_states"))
        self.session.execute(text("DELETE FROM sim_payments"))
        self.session.execute(text("DELETE FROM sim_policies"))
        self.session.commit()
