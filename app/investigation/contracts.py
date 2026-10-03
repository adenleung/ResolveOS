from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "specialist-1.1"
ROLES = frozenset({"TRANSACTION", "TECHNOLOGY", "RISK"})
HANDLERS = frozenset("INVESTIGATE_" + role for role in ROLES)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Finding(StrictModel):
    claim: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(max_length=100)
    assessment: Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "NOT_EVALUATED"]
    # Exact observed field equality is the initial deterministic support predicate.
    field: str | None = None
    expected_value: str | int | bool | None = None

class Hypothesis(StrictModel):
    possible_cause: str = Field(min_length=1, max_length=1000)
    supporting_evidence_ids: list[str] = Field(max_length=100)
    contradicting_evidence_ids: list[str] = Field(max_length=100)
    unresolved_questions: list[str] = Field(max_length=20)

class Output(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    outcome: Literal["COMPLETED", "NEEDS_ADDITIONAL_EVIDENCE", "ESCALATION_REQUIRED"]
    findings: list[Finding] = Field(max_length=50)
    hypotheses: list[Hypothesis] = Field(max_length=20)
    missing_evidence: list[str] = Field(max_length=30)
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
