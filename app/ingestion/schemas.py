from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=255)
    source_system: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    entity_reference: str = Field(min_length=1, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=255)
    occurred_at: datetime
    schema_version: str = Field(default="1.0", min_length=1, max_length=20)
    source_record_reference: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)