"""Offline deterministic projection checks; no PostgreSQL or model provider needed."""
import copy
import json
from types import SimpleNamespace

import pytest

from app.execution.simulation import SIMULATION_VERSION, project_confirmation


def authorization():
    payment = {"id": "synthetic-db-row", "payment_id": "p-123", "status": "SETTLED",
               "amount": "100.00", "currency": "SGD", "idempotency_key": "unique-123"}
    ledger = [{"ledger_transaction_id": "ledger-123", "entry_type": "DEBIT", "status": "POSTED",
               "amount": "100.00", "currency": "SGD"}]
    return SimpleNamespace(action={"action_type": "REPLAY_CONFIRMATION", "payment_id": "p-123",
        "idempotency_key": "request-123"}, snapshot={"policy_hash": "example-policy-hash",
        "source": {"bank": {"payment": payment, "ledger": ledger, "confirmations": []},
                   "events": [{"id": "source-payment-event"}], "affected_cases": 1}})


def simulate(auth):
    return project_confirmation(auth, "resolveos-confirmation-event-123")


def test_allowed_projection_is_deterministic_bounded_and_never_mutates_input():
    auth = authorization()
    original = copy.deepcopy(auth.snapshot)
    first, second = simulate(auth), simulate(auth)
    assert first == second
    assert first["schema_version"] == SIMULATION_VERSION
    assert first["outcome"] == "PASS" and not first["reasons"]
    assert first["expected"]["additional_ledger_entry_count"] == 0
    assert first["expected"]["additional_payment_count"] == 0
    assert first["expected"]["additional_confirmation_count"] == 1
    assert first["expected"]["event_processing_status"] == "PROCESSED"
    assert first["expected"]["monetary_state_unchanged"] == {
        "payment": original["source"]["bank"]["payment"],
        "ledger": original["source"]["bank"]["ledger"]}
    assert auth.snapshot == original
    json.dumps(first)


@pytest.mark.parametrize("change,reason", [
    (lambda a: a.action.update(action_type="TRANSFER"), "unsupported_counterfactual_action"),
    (lambda a: a.snapshot["source"]["bank"].update(payment=None), "source_state_incomplete"),
    (lambda a: a.snapshot["source"]["bank"]["payment"].update(status="HOLD"), "payment_not_eligible"),
    (lambda a: a.snapshot["source"]["bank"]["payment"].update(amount="NaN"), "payment_amount_invalid"),
    (lambda a: a.snapshot["source"]["bank"]["payment"].update(payment_id="other"), "payment_not_eligible"),
    (lambda a: a.snapshot["source"]["bank"]["ledger"].clear(), "duplicate_or_missing_debit"),
    (lambda a: a.snapshot["source"]["bank"]["ledger"].append(
        dict(a.snapshot["source"]["bank"]["ledger"][0])), "duplicate_or_missing_debit"),
    (lambda a: a.snapshot["source"]["bank"]["ledger"][0].update(amount="200"), "ledger_payment_disagreement"),
    (lambda a: a.snapshot["source"]["bank"]["confirmations"].append({"status": "PENDING"}), "existing_confirmation_or_uncertain_state"),
    (lambda a: a.snapshot["source"].update(events=[]), "source_evidence_missing"),
    (lambda a: a.snapshot["source"].update(events=[{"source_system": "confirmations", "status": "PENDING"}]),
        "unresolved_confirmation_observation"),
    (lambda a: a.snapshot.update(policy_hash=None), "policy_binding_missing"),
    (lambda a: a.snapshot["source"]["bank"]["payment"].update(idempotency_key=""), "payment_identity_missing"),
])
def test_counterfactual_fail_closed_on_unknown_or_conflicting_state(change, reason):
    auth = authorization()
    change(auth)
    result = simulate(auth)
    assert result["outcome"] == "BLOCKED"
    assert reason in result["reasons"]
    assert result["expected"] is None


def test_policy_and_observation_identity_bound_to_projection():
    auth = authorization()
    initial = simulate(auth)
    auth.snapshot["policy_hash"] = "next-policy"
    assert simulate(auth)["policy_hash"] != initial["policy_hash"]
    auth.snapshot["source"]["events"].append({"id": "new-evidence"})
    assert simulate(auth)["source_hash"] != initial["source_hash"]
    auth.action["idempotency_key"] = "different-request"
    assert simulate(auth)["action_hash"] != initial["action_hash"]


def test_projection_does_not_depend_on_hidden_simulator_labels():
    auth = authorization()
    result = simulate(auth)
    assert "expected_root_cause" not in str(result)
    assert "scenario_name" not in str(result)
