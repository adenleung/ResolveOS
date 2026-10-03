from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.controls.contracts import ActionRequest


class ShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supervisor_review_id: str = Field(min_length=1, max_length=200)
    policy_version_id: str = Field(min_length=1, max_length=200)
    action: ActionRequest


class ShadowResult(BaseModel):
    id: str
    case_id: str
    actor: str
    mode: Literal["SHADOW"]
    action_authorization: Literal["NOT_EVALUATED"]
    execution_permitted: Literal[False]
    outcome: str
    result: dict
    created_at: datetime


class ReplayReport(BaseModel):
    case_id: str
    as_of: datetime
    evidence_known_at_time: list[dict]
    evidence_observed_later: list[dict]
    timeline: list[dict]
    truncated: bool
    reconstruction_limitations: list[str]
    action_authorization: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
