"""Adversarial field predicates: missing data is not an observed JSON null."""
import pytest
from app.investigation.validation import validate_output


def evaluate(payloads, expected="OK"):
    events = [{"id": str(i), "payload": payload} for i, payload in enumerate(payloads)]
    output = dict(summary="Predicate evaluation", outcome="COMPLETED", findings=[dict(
        claim="Observed status", evidence_ids=[event["id"] for event in events],
        assessment="SUPPORTED", field="status", expected_value=expected)], hypotheses=[],
        missing_evidence=[], contradictions=[], suggested_next_steps=[],
        proposed_resolution=None, action_authorization="NOT_EVALUATED")
    return validate_output(output, {"events": events, "truncated": False}, {e["id"] for e in events})


@pytest.mark.parametrize("payloads,expected,assessment", [
    ([{"status": "OK"}, {}], "OK", "INSUFFICIENT_EVIDENCE"),
    ([{}, {"status": "FAILED"}], "OK", "CONTRADICTED"),
    ([{}, {}], None, "INSUFFICIENT_EVIDENCE"),
    ([{"status": None}], None, "SUPPORTED"),
    ([{"status": True}], 1, "CONTRADICTED"),
    ([{"status": 1}], True, "CONTRADICTED"),
])
def test_all_citations_must_support_exact_field(payloads, expected, assessment):
    result = evaluate(payloads, expected)
    assert result["findings"][0]["assessment"] == assessment
    assert result["outcome"] == ("COMPLETED" if assessment == "SUPPORTED" else "NEEDS_ADDITIONAL_EVIDENCE")
