from app.investigation.contracts import Output

class EvidenceRejected(ValueError):
    pass

def validate_output(output, context, retrieved):
    output = Output.model_validate(output)
    events = {row["id"]: row for row in context["events"] if row["id"] in retrieved}
    findings = []
    for finding in output.findings:
        if any(ref not in events for ref in finding.evidence_ids):
            raise EvidenceRejected("fabricated_or_unretrieved_evidence")
        value = finding.model_dump()
        value["verification"] = "UNVERIFIED_INTERPRETATION"
        if not finding.evidence_ids:
            value["assessment"] = "INSUFFICIENT_EVIDENCE"
        elif finding.field:
            observations = [events[ref]["payload"][finding.field] for ref in finding.evidence_ids
                            if finding.field in events[ref]["payload"]]
            if not observations:
                value["assessment"] = "INSUFFICIENT_EVIDENCE"
            else:
                matches = [type(item) is type(finding.expected_value) and item == finding.expected_value for item in observations]
                value["assessment"] = "SUPPORTED" if all(matches) else "CONTRADICTED"
                value["verification"] = "OBSERVED_FIELD_EQUALITY"
                # Only the predicate is verified, never arbitrary surrounding model prose.
                value["verified_observation"] = {"field": finding.field, "expected_value": finding.expected_value,
                                                 "observed_values": observations}
        else:
            value["assessment"] = "NOT_EVALUATED"
        findings.append(value)
    for hypothesis in output.hypotheses:
        refs = hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
        if not refs or any(ref not in events for ref in refs):
            raise EvidenceRejected("hypothesis_evidence_invalid")
    result = output.model_dump()
    result["findings"] = findings
    if (not findings or output.missing_evidence or output.contradictions or context["truncated"]
            or any(item["assessment"] != "SUPPORTED" for item in findings)) and output.outcome == "COMPLETED":
        result["outcome"] = "NEEDS_ADDITIONAL_EVIDENCE"
    return result
