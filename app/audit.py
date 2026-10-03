from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuditEventType(str, Enum):
    CASE_CREATED = "case_created"
    CASE_STATE_CHANGED = "case_state_changed"
    DECISION_CREATED = "decision_created"
    ACTION_ATTEMPTED = "action_attempted"
    VERIFICATION_RESULT = "verification_result"
    HUMAN_APPROVAL = "human_approval"
    POLICY_UPDATED = "policy_updated"


@dataclass(slots=True)
class AuditEvent:
    entity_type: str
    entity_id: str
    event_type: AuditEventType
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
