from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal["REPLAY_CONFIRMATION"]
    payment_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=16, max_length=200)

class ControlPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_schema: Literal["synthetic-controls-1.0"]
    action_allowlist: list[Literal["REPLAY_CONFIRMATION"]] = Field(min_length=1, max_length=1)
    worker_roles: list[Literal["WORKER"]] = Field(min_length=1, max_length=1)
    approval_role: Literal["OPERATIONS_REVIEWER"]
    max_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    max_affected_cases: int = Field(ge=1, le=500)
    max_blast_radius: int = Field(ge=1, le=1)
    human_approval_required: bool
    automatic_amount_limit: Decimal = Field(ge=0)
    approval_ttl_seconds: int = Field(ge=1, le=86400)
    authorization_ttl_seconds: int = Field(ge=1, le=86400)
    effective_to: datetime
    compensation: Literal["NONE_CONFIRMATION_ONLY"]

    @field_validator("effective_to")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return value
