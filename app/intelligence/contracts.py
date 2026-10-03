from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.orchestration.auth import Identity


@dataclass(frozen=True)
class AnalyticsAccess:
    """Server-derived scope; never constructed from request/model fields."""
    identity: Identity
    case_ids: frozenset[str] | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(StrictModel):
    kind: str
    id: str
    case_id: str | None = None


class Finding(StrictModel):
    key: str
    count: int
    case_ids: list[str]
    references: list[Reference]
    method: str
    limitation: str


class DurationMetric(StrictModel):
    key: str
    completed: int
    incomplete: int
    invalid_order: int
    median_seconds: float | None
    maximum_seconds: float | None
    references: list[Reference]
    method: str


class Hypothesis(StrictModel):
    suspected_factor: str
    supporting_evidence: list[Reference]
    contradictory_evidence: list[Reference]
    affected_cases: list[str]
    missing_information: list[str]
    next_step: str
    confidence_limitation: str


class IntelligenceReport(StrictModel):
    version: Literal["operational-intelligence-1.0"]
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    case_count: int
    truncated: bool
    limits: dict[str, int]
    overview: dict[str, int]
    categories: list[Finding]
    systems: list[Finding]
    recurrences: list[Finding]
    bottlenecks: list[DurationMetric]
    hypotheses: list[Hypothesis]
    prevention: list[Hypothesis]
    limitations: list[str]
    action_authorization: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"


class IncidentRelationships(StrictModel):
    incident_id: str
    case_ids: list[str]
    memberships: list[dict]
    history: list[dict]
    shared_observations: list[dict]
    contradictions: list[dict]
    truncated: bool
    limitation: str
    action_authorization: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
