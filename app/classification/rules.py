from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.ingestion.models import EventRecord


CLASSIFICATION_RULE_VERSION = "classification-rules-1.0"
SUCCESS_PAYMENT_STATES = {"SETTLED", "SUCCESS", "SUCCEEDED", "COMPLETED"}
CONFIRMED_STATES = {"CONFIRMED", "SUCCESS", "SUCCEEDED"}
INCOMPLETE_WORKFLOW_STATES = {
    "PENDING",
    "PROCESSING",
    "RECONCILING",
    "AWAITING_CONFIRMATION",
    "WAITING_FOR_RETRY",
    "WAITING_FOR_LATE_EVENT",
    "INVESTIGATING",
    "DOCUMENT_REQUIRED",
    "REVIEW_REQUIRED",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evidence_reference(event: EventRecord) -> dict[str, str]:
    return {
        "event_record_id": event.id,
        "event_id": event.event_id,
        "source_system": event.source_system,
        "entity_reference": event.entity_reference,
        "source_record_reference": event.source_record_reference,
    }


class Classifier(Protocol):
    source: str
    rule_version: str

    def classify(
        self,
        exception_type: str,
        events: list[EventRecord],
        classified_at: datetime,
        confirmation_window: timedelta,
        workflow_deadline: timedelta,
        missing_evidence: bool,
    ) -> dict[str, Any]: ...


class RuleBasedClassifier:
    source = "deterministic_rules"
    rule_version = CLASSIFICATION_RULE_VERSION

    def classify(
        self,
        exception_type: str,
        events: list[EventRecord],
        classified_at: datetime,
        confirmation_window: timedelta,
        workflow_deadline: timedelta,
        missing_evidence: bool,
    ) -> dict[str, Any]:
        now = _utc(classified_at)
        categories: dict[str, dict[str, Any]] = {}

        def add(
            category: str,
            rule: str,
            explanation: str,
            supporting: list[EventRecord],
            features: dict[str, Any],
        ) -> None:
            result = categories.setdefault(
                category,
                {
                    "category": category,
                    "rule": rule,
                    "rule_version": self.rule_version,
                    "explanation": explanation,
                    "supporting_evidence_references": [],
                    "features": {},
                },
            )
            known = {reference["event_record_id"] for reference in result["supporting_evidence_references"]}
            for event in supporting:
                if event.id not in known:
                    result["supporting_evidence_references"].append(evidence_reference(event))
                    known.add(event.id)
            result["features"].update(features)

        payments = self._latest(events, "payments")
        confirmations = [event for event in events if event.source_system == "confirmations"]
        successful_confirmation = [
            event
            for event in confirmations
            if str(event.payload.get("confirmation_status", "")).upper() in CONFIRMED_STATES
            and _utc(event.occurred_at) <= now
        ]
        for payment in payments:
            status = str(payment.payload.get("payment_status", "")).upper()
            age_seconds = (now - _utc(payment.occurred_at)).total_seconds()
            if (
                status in SUCCESS_PAYMENT_STATES | {"PENDING"}
                and not successful_confirmation
                and age_seconds >= confirmation_window.total_seconds()
            ):
                add(
                    "PAYMENT_CONFIRMATION_MISMATCH",
                    "payment.confirmation-window-expired",
                    "Payment state requires confirmation, but no successful confirmation was observed by the configured deadline.",
                    [payment],
                    {"payment_status": status, "confirmation_observed": False, "window_elapsed": True},
                )

        ledgers = self._latest(events, "ledger")
        for payment in payments:
            for ledger in ledgers:
                amount_mismatch = str(payment.payload.get("amount")) != str(ledger.payload.get("amount"))
                currency_mismatch = str(payment.payload.get("currency")) != str(ledger.payload.get("currency"))
                if amount_mismatch or currency_mismatch:
                    add(
                        "RECONCILIATION_MISMATCH",
                        "reconciliation.payment-ledger-values-disagree",
                        "Observed payment and ledger amount or currency values differ.",
                        [payment, ledger],
                        {
                            "payment_amount": payment.payload.get("amount"),
                            "ledger_amount": ledger.payload.get("amount"),
                            "payment_currency": payment.payload.get("currency"),
                            "ledger_currency": ledger.payload.get("currency"),
                        },
                    )

        latest_workflows = self._latest(events, "workflow")
        for payment in payments:
            payment_status = str(payment.payload.get("payment_status", "")).upper()
            for confirmation in confirmations:
                confirmation_status = str(confirmation.payload.get("confirmation_status", "")).upper()
                if confirmation_status == "CONFLICTING" or (
                    confirmation_status in CONFIRMED_STATES and payment_status not in SUCCESS_PAYMENT_STATES
                ):
                    add(
                        "CONFLICTING_RECORDS",
                        "records.payment-confirmation-state-conflict",
                        "Observed payment and confirmation records contain incompatible states.",
                        [payment, confirmation],
                        {"payment_status": payment_status, "confirmation_status": confirmation_status},
                    )

        latest_api_ids = {event.id for event in self._latest(events, "api_gateway")}
        for event in events:
            if event.source_system == "api_gateway" and event.id in latest_api_ids:
                status_code = int(event.payload.get("status_code", 0))
                latency = int(event.payload.get("latency_ms", 0))
                if status_code >= 500 or latency >= 30_000:
                    payment_context = next(
                        (payment for payment in payments if payment.entity_reference == event.entity_reference),
                        None,
                    )
                    supporting = [event] + ([payment_context] if payment_context is not None else [])
                    add(
                        "API_PROCESSING_FAILURE",
                        "technology.api-failure-or-timeout",
                        "The observed API operation failed or exceeded the synthetic timeout threshold.",
                        supporting,
                        {
                            "status_code": status_code,
                            "latency_ms": latency,
                            "error_type": event.payload.get("error_type"),
                            "payment_state_relevant": payment_context is not None,
                            "payment_status": payment_context.payload.get("payment_status") if payment_context else None,
                        },
                    )

            if event.source_system == "confirmations" and (
                bool(event.payload.get("is_duplicate"))
                or str(event.payload.get("confirmation_status", "")).upper() == "REPLAYED"
            ):
                add(
                    "DUPLICATE_EVENT",
                    "confirmation.logical-event-replayed",
                    "The confirmation source marked this logical event as repeated; this does not itself establish a duplicate payment.",
                    [event],
                    {"confirmation_status": event.payload.get("confirmation_status"), "source_marked_duplicate": True},
                )

            if event.source_system == "documents" and str(event.payload.get("document_status", "")).upper() in {
                "MISSING",
                "REJECTED",
                "EXPIRED",
            }:
                add(
                    "DOCUMENT_STATUS_EXCEPTION",
                    "documents.status-not-acceptable",
                    "The observed document status is missing, rejected, or expired.",
                    [event],
                    {"document_status": event.payload.get("document_status")},
                )

        for workflow in latest_workflows:
            status = str(workflow.payload.get("workflow_status", "")).upper()
            age_seconds = (now - _utc(workflow.occurred_at)).total_seconds()
            if status in INCOMPLETE_WORKFLOW_STATES and age_seconds >= workflow_deadline.total_seconds():
                add(
                    "WORKFLOW_EXCEPTION",
                    "workflow.incomplete-past-deadline",
                    "The latest observed workflow state remained incomplete past its configured deadline.",
                    [workflow],
                    {"workflow_status": status, "deadline_elapsed": True},
                )

        uncertainty_flags: list[str] = []
        if missing_evidence or not events:
            uncertainty_flags.append("missing_evidence")
        if "CONFLICTING_RECORDS" in categories:
            uncertainty_flags.append("conflicting_evidence")
        if not categories:
            uncertainty_flags.append("unsupported_condition")
            refs = [evidence_reference(event) for event in events]
            categories["UNKNOWN_EXCEPTION"] = {
                "category": "UNKNOWN_EXCEPTION",
                "rule": "fallback.no-supported-rule-matched",
                "rule_version": self.rule_version,
                "explanation": f"No supported deterministic rule matched exception type {exception_type!r}.",
                "supporting_evidence_references": refs,
                "features": {"observed_exception_type": exception_type, "observed_event_count": len(events)},
            }

        ordered_categories = [categories[key] for key in sorted(categories)]
        references_by_id: dict[str, dict[str, str]] = {}
        for category in ordered_categories:
            for reference in category["supporting_evidence_references"]:
                references_by_id.setdefault(reference["event_record_id"], reference)
        operational_eligible = not any(
            flag in uncertainty_flags for flag in ("missing_evidence", "conflicting_evidence", "unsupported_condition")
        )
        return {
            "categories": ordered_categories,
            "classification_timestamp": now.isoformat(),
            "classification_source": self.source,
            "rule_version": self.rule_version,
            "score": None,
            "operational_eligible": operational_eligible,
            "supporting_evidence_references": list(references_by_id.values()),
            "uncertainty_flags": uncertainty_flags,
            "explanation": " ".join(category["explanation"] for category in ordered_categories),
        }

    @staticmethod
    def _latest(events: list[EventRecord], source_system: str) -> list[EventRecord]:
        latest: dict[str, EventRecord] = {}
        for event in events:
            if event.source_system != source_system:
                continue
            previous = latest.get(event.source_record_reference)
            current_order = (_utc(event.occurred_at), _utc(event.ingested_at))
            previous_order = (_utc(previous.occurred_at), _utc(previous.ingested_at)) if previous else None
            if previous is None or current_order > previous_order:
                latest[event.source_record_reference] = event
        return list(latest.values())