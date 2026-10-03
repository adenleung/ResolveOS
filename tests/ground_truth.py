SCENARIO_GROUND_TRUTH = {
    "normal_success": {
        "expected_status": "SETTLED",
        "root_cause": "none",
        "expected_outcome": "completed",
    },
    "missing_confirmation": {
        "expected_status": "PENDING",
        "root_cause": "missing_confirmation_event",
        "expected_outcome": "pending_confirmation",
    },
    "payment_status_mismatch": {
        "expected_status": "PENDING",
        "root_cause": "payment_status_mismatch",
        "expected_outcome": "status_mismatch",
    },
    "ledger_reconciliation_mismatch": {
        "expected_status": "HOLD",
        "root_cause": "ledger_balance_discrepancy",
        "expected_outcome": "reconciliation_mismatch",
    },
    "api_timeout": {
        "expected_status": "TIMEOUT",
        "root_cause": "technology_timeout",
        "expected_outcome": "api_timeout",
    },
    "duplicate_event": {
        "expected_status": "RETRY",
        "root_cause": "duplicate_confirmation",
        "expected_outcome": "duplicate_event_detected",
    },
    "duplicate_payment_risk": {
        "expected_status": "HOLD",
        "root_cause": "duplicate_idempotency_risk",
        "expected_outcome": "duplicate_payment_risk",
    },
    "delayed_event": {
        "expected_status": "PENDING",
        "root_cause": "late_event_arrival",
        "expected_outcome": "delayed_confirmation",
    },
    "partial_processing_failure": {
        "expected_status": "FAILED",
        "root_cause": "partial_processing_failure",
        "expected_outcome": "partial_failure",
    },
    "conflicting_system_records": {
        "expected_status": "INVESTIGATING",
        "root_cause": "conflicting_source_records",
        "expected_outcome": "conflicting_records",
    },
    "missing_document": {
        "expected_status": "HOLD",
        "root_cause": "missing_document",
        "expected_outcome": "document_missing",
    },
    "shared_incident_multiple_exceptions": {
        "expected_status": "INVESTIGATING",
        "root_cause": "shared_incident_root_cause",
        "expected_outcome": "multi_exception_shared_incident",
    },
    "similar_look_but_different_causes": {
        "expected_status": "HOLD",
        "root_cause": "misleading_similarity",
        "expected_outcome": "similar_look_different_causes",
    },
}
