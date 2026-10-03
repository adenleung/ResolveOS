from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.classification.rules import _utc
from app.ingestion.models import EventRecord


SYNTHETIC_PRIORITY_CONFIGURATION: dict[str, Any] = {
    "version": "synthetic-priority-1.0",
    "amount_impact_threshold": "5000.00",
    "case_age_urgency_hours": 4,
    "system_criticality": {
        "payments": 3,
        "ledger": 3,
        "confirmations": 2,
        "api_gateway": 2,
        "workflow": 1,
        "documents": 1,
    },
    "sla_hours": {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 24, "LOW": 72},
    "levels": {"CRITICAL": 7, "HIGH": 4, "MEDIUM": 2},
}

SPECIALIST_ORDER = ("TRANSACTION", "TECHNOLOGY", "RISK", "DOCUMENT", "COMPLIANCE", "WORKFLOW")
ROUTING_RULE_VERSION = "specialist-routing-1.0"


class PriorityEngine:
    def __init__(self, configuration: dict[str, Any] | None = None):
        self.configuration = configuration or SYNTHETIC_PRIORITY_CONFIGURATION

    def calculate(
        self,
        categories: list[dict[str, Any]],
        events: list[EventRecord],
        all_payment_events: list[EventRecord],
        case_created_at: datetime,
        now: datetime,
        evidence_complete: bool,
    ) -> dict[str, Any]:
        category_names = {category["category"] for category in categories}
        entities_by_key: dict[str, set[str]] = {}
        latest_payment_events: dict[str, EventRecord] = {}
        for event in all_payment_events:
            previous = latest_payment_events.get(event.entity_reference)
            if previous is None or (_utc(event.occurred_at), _utc(event.ingested_at)) > (
                _utc(previous.occurred_at), _utc(previous.ingested_at)
            ):
                latest_payment_events[event.entity_reference] = event
        for entity, event in latest_payment_events.items():
            key = event.payload.get("idempotency_key")
            if key:
                entities_by_key.setdefault(str(key), set()).add(entity)
        current_entities = {event.entity_reference for event in events}
        current_payments = [event for event in latest_payment_events.values() if event.entity_reference in current_entities]
        current_keys = {
            str(event.payload.get("idempotency_key")) for event in current_payments if event.payload.get("idempotency_key")
        }
        duplicate_keys = {key for key in current_keys if len(entities_by_key.get(key, set())) > 1}
        duplicate_effect_risk = bool(duplicate_keys)
        duplicate_payment_refs = [
            {
                "event_record_id": event.id,
                "event_id": event.event_id,
                "source_system": event.source_system,
                "entity_reference": event.entity_reference,
                "source_record_reference": event.source_record_reference,
            }
            for event in latest_payment_events.values()
            if str(event.payload.get("idempotency_key")) in duplicate_keys
        ]

        latest_payments = current_payments
        amount = Decimal("0")
        for event in latest_payments:
            try:
                amount = max(amount, Decimal(str(event.payload.get("amount", "0"))))
            except InvalidOperation:
                continue

        sources = {event.source_system for event in events}
        criticality = max(
            (self.configuration["system_criticality"].get(source, 0) for source in sources),
            default=0,
        )
        record_count = len({(event.source_system, event.source_record_reference) for event in events})
        age_hours = max(0, (_utc(now) - _utc(case_created_at)).total_seconds() / 3600)
        age_urgent = age_hours >= self.configuration["case_age_urgency_hours"]

        score = 0
        applied_rules: list[str] = []
        impact_categories = {
            "RECONCILIATION_MISMATCH",
            "CONFLICTING_RECORDS",
        }
        if category_names & impact_categories:
            score += 2
            applied_rules.append("priority.material-financial-or-state-impact")
        if category_names & {"API_PROCESSING_FAILURE", "WORKFLOW_EXCEPTION", "PAYMENT_CONFIRMATION_MISMATCH", "DUPLICATE_EVENT", "DOCUMENT_STATUS_EXCEPTION"}:
            score += 1
            applied_rules.append("priority.operational-exception")
        if amount >= Decimal(str(self.configuration["amount_impact_threshold"])):
            score += 2
            applied_rules.append("priority.amount-impact-threshold")
        if duplicate_effect_risk:
            score += 5
            applied_rules.append("priority.potential-duplicate-monetary-effect")
        if record_count >= 4:
            score += 1
            applied_rules.append("priority.multiple-affected-records")
        if criticality >= 3:
            score += 2
            applied_rules.append("priority.critical-system")
        elif criticality == 2:
            score += 1
            applied_rules.append("priority.high-criticality-system")
        if age_urgent:
            score += 1
            applied_rules.append("priority.case-age-urgency")
        if not evidence_complete:
            score += 1
            applied_rules.append("priority.incomplete-evidence-review")
        thresholds = self.configuration["levels"]
        level = "CRITICAL" if score >= thresholds["CRITICAL"] else (
            "HIGH" if score >= thresholds["HIGH"] else "MEDIUM" if score >= thresholds["MEDIUM"] else "LOW"
        )
        hours = int(self.configuration["sla_hours"][level])
        return {
            "level": level,
            "score": score,
            "rule_version": self.configuration["version"],
            "applied_rules": applied_rules,
            "input_facts": {
                "maximum_observed_payment_amount": str(amount),
                "amount_impact_threshold": str(self.configuration["amount_impact_threshold"]),
                "affected_source_record_count": record_count,
                "potential_duplicate_monetary_effect": duplicate_effect_risk,
                "potential_duplicate_payment_evidence": duplicate_payment_refs,
                "system_criticality_score": criticality,
                "system_criticality_sources": sorted(sources),
                "case_age_urgency_applied": age_urgent,
                "evidence_complete": evidence_complete,
            },
            "sla_duration_hours": hours,
            "action_authorization": "NOT_EVALUATED",
        }


def recommend_routing(
    categories: list[dict[str, Any]],
    events: list[EventRecord],
    uncertainty_flags: list[str],
    duplicate_effect_risk: bool = False,
) -> dict[str, Any]:
    names = {category["category"] for category in categories}
    specialists: set[str] = set()
    rules: list[str] = []
    if "PAYMENT_CONFIRMATION_MISMATCH" in names:
        specialists.update({"TRANSACTION", "TECHNOLOGY"})
        rules.append("route.payment-confirmation-to-transaction-technology")
    if "RECONCILIATION_MISMATCH" in names:
        specialists.update({"TRANSACTION", "RISK"})
        rules.append("route.reconciliation-to-transaction-risk")
    if "API_PROCESSING_FAILURE" in names:
        specialists.add("TECHNOLOGY")
        rules.append("route.api-failure-to-technology")
        if any(event.source_system == "payments" for event in events):
            specialists.add("TRANSACTION")
            rules.append("route.api-failure-with-payment-state-to-transaction")
    if "WORKFLOW_EXCEPTION" in names:
        specialists.add("WORKFLOW")
        rules.append("route.workflow-to-workflow-specialist")
    if "CONFLICTING_RECORDS" in names:
        specialists.update({"TRANSACTION", "RISK"})
        rules.append("route.conflicting-records-to-transaction-risk")
    if "DUPLICATE_EVENT" in names:
        specialists.add("TRANSACTION")
        rules.append("route.duplicate-event-to-transaction")
        if duplicate_effect_risk:
            specialists.add("RISK")
            rules.append("route.duplicate-effect-risk-to-risk")
    if "DOCUMENT_STATUS_EXCEPTION" in names:
        specialists.update({"DOCUMENT", "COMPLIANCE"})
        rules.append("route.document-status-to-document-compliance")

    triage_required = bool(uncertainty_flags) or not specialists
    ordered = [specialist for specialist in SPECIALIST_ORDER if specialist in specialists]
    return {
        "recommended_specialists": ordered,
        "fallback_queue": "HUMAN_TRIAGE" if triage_required else None,
        "human_triage_required": triage_required,
        "rule_version": ROUTING_RULE_VERSION,
        "applied_rules": rules,
        "explanation": "Deterministic specialist recommendations based on observed categories and source attributes; routing does not authorize actions.",
    }