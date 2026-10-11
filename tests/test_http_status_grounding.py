import pytest
from pydantic import ValidationError
from app.investigation.contracts import Finding, Output
from app.investigation.validation import validate_output, EvidenceRejected


def result(expected, observed=504, refs=None, retrieved=None, field="status_code"):
    output = dict(summary="Observed predicate", outcome="COMPLETED", findings=[dict(
        claim="Status observation", field=field, expected_value=expected,
        evidence_ids=["event"] if refs is None else refs, assessment="SUPPORTED")], hypotheses=[],
        missing_evidence=[], contradictions=[], suggested_next_steps=[], proposed_resolution=None,
        action_authorization="NOT_EVALUATED")
    return validate_output(output, {"events":[dict(id="event", payload={field:observed})], "truncated":False},
                           {"event"} if retrieved is None else retrieved)


@pytest.mark.parametrize("expected", [504, "504"])
def test_http_504_canonical_integer(expected):
    finding = result(expected)["findings"][0]
    assert finding["assessment"]=="SUPPORTED"
    assert type(finding["expected_value"]) is int and finding["expected_value"]==504


@pytest.mark.parametrize("expected", [" 504", "504 ", "+504", "0504", "504.0", "5.04e2", "５０４", "099", "600", 99, 600, True, 504.0, None])
def test_invalid_http_status_rejected(expected):
    with pytest.raises(ValidationError): result(expected)


@pytest.mark.parametrize("observed", [200, "504", True, None])
def test_no_evidence_coercion_or_mismatch_support(observed):
    assert result("504", observed)["findings"][0]["assessment"]=="CONTRADICTED"


def test_no_global_numeric_coercion():
    assert result("504", 504, field="amount")["findings"][0]["assessment"]=="CONTRADICTED"


@pytest.mark.parametrize("refs,retrieved", [(["foreign"], {"event"}), (["event"], set())])
def test_wrong_or_unretrieved_citation_still_rejected(refs, retrieved):
    with pytest.raises(EvidenceRejected): result("504", refs=refs, retrieved=retrieved)


def test_uncited_claim_stays_insufficient():
    assert result("504", refs=[])["findings"][0]["assessment"]=="INSUFFICIENT_EVIDENCE"


def test_wrong_source_field_cannot_support_status():
    finding = dict(claim="HTTP status", field="status_code", expected_value="504", evidence_ids=["event"], assessment="SUPPORTED")
    output = dict(summary="Observed predicate", outcome="COMPLETED", findings=[finding], hypotheses=[],
        missing_evidence=[], contradictions=[], suggested_next_steps=[], proposed_resolution=None, action_authorization="NOT_EVALUATED")
    validated = validate_output(output, {"events":[dict(id="event", payload={"amount":504})], "truncated":False}, {"event"})
    assert validated["findings"][0]["assessment"]=="INSUFFICIENT_EVIDENCE"
    assert validated["outcome"]=="NEEDS_ADDITIONAL_EVIDENCE"


def test_conversion_has_explicit_audit_record():
    assert result("504")["findings"][0]["normalization"]==dict(rule="http-status-canonical-ascii-v1", original_value="504", original_type="string")


def test_specialist_and_supervisor_provider_schemas_require_integer_status():
    from app.investigation.contracts import SupervisorOutput
    from app.investigation.provider import output_schema
    for model in (Output, SupervisorOutput):
        status, generic = output_schema(model)["$defs"]["Finding"]["anyOf"]
        assert status["properties"]["field"]["enum"]==["status_code"]
        assert status["properties"]["expected_value"]==dict(type="integer", minimum=100, maximum=599)
        assert "status_code" not in generic["properties"]["field"]["anyOf"][0]["enum"]
        assert status["additionalProperties"] is False
