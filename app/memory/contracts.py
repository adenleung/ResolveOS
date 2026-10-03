from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.orchestration.auth import Identity

LABEL = "HISTORICAL CONTEXT — NOT CURRENT EVIDENCE OR AUTHORIZATION."
GOVERNANCE_VERSION = "reviewed-memory-1.0"


@dataclass(frozen=True)
class MemoryAccess:
    """Server-issued capability, never populated from model arguments or HTTP bodies.

    None inherits existing broad development operational access. Production adapters
    must supply explicit case and source grants; missing grants fail closed.
    """
    identity: Identity
    case_ids: frozenset[str] | None = None
    source_systems: frozenset[str] | None = None


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=200)
    verification_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    failure_pattern: str = Field(default="", max_length=300)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["SUBMIT", "APPROVE", "REJECT", "REVOKE", "WITHDRAW", "FLAG", "CORRECT"]
    reason: str = Field(min_length=1, max_length=1000)
    summary: str | None = Field(default=None, min_length=1, max_length=1000)
    failure_pattern: str | None = Field(default=None, max_length=300)
    verification_id: str | None = Field(default=None, min_length=1, max_length=200)
    evidence_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)
