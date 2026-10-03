"""Read-only, bounded counterfactual for ONE synthetic confirmation-only action.

A projection is neither evidence that an effect occurred nor authorization to act.
Input is the already observed, explicitly selected source columns in Controls;
never read simulator ground-truth labels, mutate tables, or call a model.
"""
from decimal import Decimal, InvalidOperation

from app.orchestration.queue import digest

SIMULATION_VERSION = "confirmation-counterfactual-1.0"


def project_confirmation(authorization, event_id):
    """Compute a deterministic, JSON-compatible hypothetical state transition."""
    action = authorization.action or {}
    snapshot = authorization.snapshot or {}
    source = snapshot.get("source") or {}
    bank = source.get("bank") or {}
    payment = bank.get("payment")
    ledger = bank.get("ledger")
    confirmations = bank.get("confirmations")
    issues = []
    if action.get("action_type") != "REPLAY_CONFIRMATION" or not isinstance(action.get("payment_id"), str):
        issues.append("unsupported_counterfactual_action")
    if payment is None or not isinstance(ledger, list) or not isinstance(confirmations, list):
        issues.append("source_state_incomplete")
    elif not isinstance(payment, dict):
        issues.append("source_state_invalid")
    else:
        if payment.get("payment_id") != action.get("payment_id") or payment.get("status") != "SETTLED":
            issues.append("payment_not_eligible")
        if not isinstance(payment.get("idempotency_key"), str) or not payment["idempotency_key"]:
            issues.append("payment_identity_missing")
        try:
            amount = Decimal(str(payment.get("amount")))
            if not amount.is_finite() or amount <= 0:
                issues.append("payment_amount_invalid")
        except (InvalidOperation, TypeError):
            issues.append("payment_amount_invalid")
            amount = None
        if not isinstance(payment.get("currency"), str) or not payment["currency"]:
            issues.append("payment_currency_missing")
        if confirmations:
            issues.append("existing_confirmation_or_uncertain_state")
        if len(ledger) > 2:
            issues.append("ledger_effects_uncertain")
        debits = [entry for entry in ledger if isinstance(entry, dict) and entry.get("entry_type") == "DEBIT"
                  and entry.get("status") == "POSTED"]
        if len(debits) != 1:
            issues.append("duplicate_or_missing_debit")
        for entry in ledger:
            if not isinstance(entry, dict) or entry.get("entry_type") not in {"DEBIT", "CREDIT"} or entry.get("status") != "POSTED":
                issues.append("ledger_effects_uncertain")
                continue
            try:
                same_amount = amount is not None and Decimal(str(entry.get("amount"))) == amount
            except (InvalidOperation, TypeError):
                same_amount = False
            if not same_amount or entry.get("currency") != payment.get("currency"):
                issues.append("ledger_payment_disagreement")
        if len([entry for entry in ledger if isinstance(entry, dict) and entry.get("entry_type") == "CREDIT"]) > 1:
            issues.append("ledger_effects_uncertain")
    if not isinstance(source.get("events"), list) or not source["events"]:
        issues.append("source_evidence_missing")
    elif any(isinstance(event, dict) and event.get("source_system") == "confirmations"
             for event in source["events"]):
        # An unaccounted-for confirmation observation is uncertainty, not consent to replay.
        issues.append("unresolved_confirmation_observation")
    if not snapshot.get("policy_hash"):
        issues.append("policy_binding_missing")
    if not event_id or not isinstance(event_id, str):
        issues.append("synthetic_event_identity_missing")
    issues = sorted(set(issues))
    return {
        "schema_version": SIMULATION_VERSION,
        "outcome": "BLOCKED" if issues else "PASS",
        "reasons": issues,
        "source_hash": digest(source),
        "policy_hash": snapshot.get("policy_hash"),
        "action_hash": digest(action),
        "expected": None if issues else {
            # These records are hypothetical only; no source rows are written.
            "monetary_state_unchanged": {"payment": payment, "ledger": ledger},
            "confirmation": {"event_id": event_id, "status": "CONFIRMED"},
            "event_processing_status": "PROCESSED",
            "additional_confirmation_count": 1,
            "additional_payment_count": 0,
            "additional_ledger_entry_count": 0,
        },
    }
