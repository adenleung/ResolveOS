from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WORKFLOW_VERSION = "case-orchestration-1.0"


class TaskType(str, Enum):
    CLASSIFY_CASE = "CLASSIFY_CASE"
    ROUTE_CASE = "ROUTE_CASE"
    REEVALUATE_CASE = "REEVALUATE_CASE"
    CHECK_SLA = "CHECK_SLA"
    INVESTIGATE_TRANSACTION = "INVESTIGATE_TRANSACTION"
    INVESTIGATE_TECHNOLOGY = "INVESTIGATE_TECHNOLOGY"
    INVESTIGATE_RISK = "INVESTIGATE_RISK"
    INVESTIGATE_WORKFLOW = "INVESTIGATE_WORKFLOW"
    INVESTIGATE_DOCUMENT = "INVESTIGATE_DOCUMENT"
    INVESTIGATE_COMPLIANCE = "INVESTIGATE_COMPLIANCE"
    REQUEST_SUPERVISOR_REVIEW = "REQUEST_SUPERVISOR_REVIEW"
    REQUEST_HUMAN_REVIEW = "REQUEST_HUMAN_REVIEW"
    PREPARE_EXECUTION = "PREPARE_EXECUTION"
    REQUEST_VERIFICATION = "REQUEST_VERIFICATION"


BUILTIN_TASKS = {TaskType.CLASSIFY_CASE.value, TaskType.ROUTE_CASE.value,
                 TaskType.REEVALUATE_CASE.value, TaskType.CHECK_SLA.value}
INVESTIGATION_TASKS = {item.value for item in TaskType if item.value.startswith("INVESTIGATE_")}
ACTIVE_TASKS = ("PENDING", "WAITING_HANDLER", "RUNNING", "RETRY_WAIT")


class TaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_version: Literal["1.0"] = "1.0"
    workflow_version: Literal["case-orchestration-1.0"] = WORKFLOW_VERSION
    case_id: str = Field(min_length=1)
    task_type: TaskType
    incident_id: str | None = None
    authorization_id: str | None = None
    action_id: str | None = None
    assessment_ids: list[str] = Field(default_factory=list, max_length=500)
    assessment_versions: dict[str, str] = Field(default_factory=dict)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    evidence_truncated: bool = False
    permitted_tool_scope: list[Literal["READ_CASE_EVIDENCE", "READ_INCIDENT_CONTEXT"]] = Field(default_factory=list)
    deadline: datetime | None = None
    incident_context: dict[str, Any] | None = None
    reason: str = Field(default="Operational case work", min_length=1, max_length=500)


class InvestigationResult(BaseModel):
    """Phase 7 result envelope. Phase 6 does not accept successful investigator results."""
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["1.0"] = "1.0"
    task_id: str
    lease_token: str
    assessment_ids: list[str]
    attempt_number: int = Field(ge=1)
    outcome: Literal["COMPLETED", "NEEDS_ADDITIONAL_EVIDENCE", "FAILED", "TIMED_OUT", "ESCALATION_REQUIRED"]
    summary: str = Field(min_length=1, max_length=4000)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    action_authorization: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
