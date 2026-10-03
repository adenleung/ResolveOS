from __future__ import annotations

from enum import Enum


class CaseState(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATION_QUEUED = "INVESTIGATION_QUEUED"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_DECISION = "AWAITING_DECISION"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    APPROVED = "APPROVED"
    EXECUTION_QUEUED = "EXECUTION_QUEUED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class CaseLifecycleService:
    valid_transitions = {
        CaseState.DETECTED: {CaseState.TRIAGED, CaseState.BLOCKED, CaseState.ESCALATED},
        CaseState.TRIAGED: {CaseState.INVESTIGATION_QUEUED, CaseState.INVESTIGATING, CaseState.AWAITING_HUMAN, CaseState.BLOCKED, CaseState.ESCALATED},
        CaseState.INVESTIGATION_QUEUED: {CaseState.INVESTIGATING, CaseState.AWAITING_HUMAN, CaseState.BLOCKED, CaseState.ESCALATED},
        CaseState.INVESTIGATING: {CaseState.INVESTIGATION_QUEUED, CaseState.AWAITING_HUMAN, CaseState.AWAITING_DECISION, CaseState.BLOCKED, CaseState.ESCALATED, CaseState.FAILED},
        CaseState.AWAITING_DECISION: {CaseState.AWAITING_HUMAN, CaseState.APPROVED, CaseState.BLOCKED, CaseState.ESCALATED},
        CaseState.AWAITING_HUMAN: {CaseState.INVESTIGATION_QUEUED, CaseState.APPROVED, CaseState.BLOCKED, CaseState.ESCALATED},
        CaseState.APPROVED: {CaseState.EXECUTION_QUEUED, CaseState.EXECUTING, CaseState.BLOCKED},
        CaseState.EXECUTION_QUEUED: {CaseState.EXECUTING, CaseState.BLOCKED},
        CaseState.EXECUTING: {CaseState.VERIFYING, CaseState.FAILED, CaseState.ESCALATED},
        CaseState.VERIFYING: {CaseState.RESOLVED, CaseState.FAILED, CaseState.ESCALATED},
        CaseState.RESOLVED: set(),
        CaseState.BLOCKED: set(),
        CaseState.ESCALATED: set(),
        CaseState.FAILED: set(),
    }

    def transition(self, current: CaseState, new_state: CaseState) -> CaseState:
        if current not in self.valid_transitions:
            raise ValueError(f"Unknown current state: {current}")
        if new_state not in self.valid_transitions[current]:
            raise ValueError(f"Invalid transition from {current.value} to {new_state.value}")
        return new_state
