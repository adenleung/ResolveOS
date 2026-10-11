from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StrictStr, StrictInt, StrictBool, model_validator

PROMPT_VERSION = "specialist-1.5"
ROLES = frozenset({"TRANSACTION", "TECHNOLOGY", "RISK"})
HANDLERS = frozenset("INVESTIGATE_" + role for role in ROLES)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Finding(StrictModel):
    claim: str = Field(min_length=1, max_length=1000, description="One observable field value at a specific source event or occurred_at time. Never combine different temporal states in one predicate; describe lifecycle chronology separately in summary.")
    evidence_ids: list[str] = Field(max_length=100, description="Every citation must independently contain and support this exact field/value predicate. Cite different temporal values in separate findings, not together under the final value.")
    assessment: Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "NOT_EVALUATED"]
    # Exact observed field equality is the initial deterministic support predicate.
    field: str | None = None
    expected_value: StrictStr | StrictInt | StrictBool | None = Field(default=None,
        description="Copy the observed JSON type. status_code requires an integer HTTP status from 100 to 599, never a quoted number.")
    _normalization: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def canonical_http_status(self):
        if self.field=="status_code":
            raw = self.expected_value
            # Compatibility with historical/injected outputs ONLY. No source
            # coercion, trimming, Unicode digits, signs, decimals or other fields.
            if type(raw) is str and len(raw)==3 and all("0"<=c<="9" for c in raw) and "100"<=raw<="599":
                self.expected_value = int(raw)
                self._normalization = dict(rule="http-status-canonical-ascii-v1", original_value=raw, original_type="string")
            elif type(raw) is not int or not 100<=raw<=599:
                raise ValueError("status_code_requires_canonical_http_integer")
        return self

class Hypothesis(StrictModel):
    possible_cause: str = Field(min_length=1, max_length=1000)
    supporting_evidence_ids: list[str] = Field(max_length=100)
    contradicting_evidence_ids: list[str] = Field(max_length=100)
    unresolved_questions: list[str] = Field(max_length=20, description="Explicit unresolved diagnostic questions; these are not established causes. Material gaps must also appear in missing_evidence.")

class Output(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    outcome: Literal["COMPLETED", "NEEDS_ADDITIONAL_EVIDENCE", "ESCALATION_REQUIRED"] = Field(description="Advisory investigation status, not causal certainty, resolution or authorization. Complete only when material source-backed assessment is possible; otherwise request evidence or escalation.")
    findings: list[Finding] = Field(max_length=50)
    hypotheses: list[Hypothesis] = Field(max_length=20)
    missing_evidence: list[str] = Field(max_length=30, description="Missing evidence material to establishing the case state, evaluating conflicting observations, or making the bounded advisory assessment. Nonblocking diagnostic unknowns belong in hypotheses.unresolved_questions; do not omit material uncertainty to obtain completion.")
    contradictions: list[str] = Field(max_length=30)
    suggested_next_steps: list[str] = Field(max_length=20)
    proposed_resolution: str | None
    action_authorization: Literal["NOT_EVALUATED"]

class ToolCall(StrictModel):
    name: str
    arguments: dict[str, Any]
    call_id: str

class SupervisorOutput(StrictModel):
    review_version: Literal["1.0"]
    outcome: Literal["RECOMMENDATION", "REINVESTIGATE", "ESCALATE"]
    summary: str = Field(min_length=1, max_length=4000)
    supported_conclusions: list[Finding] = Field(max_length=50)
    rejected_conclusions: list[str] = Field(max_length=50)
    unresolved_issues: list[str] = Field(max_length=30)
    required_additional_checks: list[str] = Field(max_length=30)
    targeted_specialists: list[Literal["TRANSACTION", "TECHNOLOGY", "RISK"]] = Field(max_length=3)
    proposed_action: str | None
    evidence_ids: list[str] = Field(max_length=100)
    escalation_reasons: list[str] = Field(max_length=30)
    action_authorization: Literal["NOT_EVALUATED"]

class ModelTurn(StrictModel):
    calls: list[ToolCall] = Field(default_factory=list, max_length=30)
    output: Output | SupervisorOutput | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
