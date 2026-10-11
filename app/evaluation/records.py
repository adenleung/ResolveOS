"""Explicit-column synthetic workflow export; excludes simulator hidden labels."""
from sqlalchemy import select
from app.models.domain import Case, AuditLog, ExceptionRecord, Evidence, VerificationResult, ActionRecord
from app.orchestration.models import WorkTask, TaskHistory
from app.investigation.models import InvestigationRun
from app.supervisor.models import SupervisorReview
from app.controls.models import ControlAuthorization, ActionApproval, ActionApprovalHistory
from app.execution.models import ExecutionOperation
from app.ingestion.models import EventRecord
from app.investigation.tools import clean_payload


def case_records(session, case_id):
    case = session.get(Case, case_id)
    entities = list(session.scalars(select(ExceptionRecord.source_reference).where(ExceptionRecord.case_id == case_id)))
    def rows(model, fields):
        query = select(*(getattr(model, field) for field in fields)).where(model.case_id == case_id)
        return [dict(row) for row in session.execute(query).mappings()]
    controls = rows(ControlAuthorization, ("id", "outcome", "reasons", "created_at", "policy_version_id"))
    approval_ids = [row["id"] for row in controls]
    events = [dict(id=event.id, event_id=event.event_id, source_system=event.source_system,
        occurred_at=event.occurred_at, ingested_at=event.ingested_at, payload=clean_payload(event.payload))
        for event in session.scalars(select(EventRecord).where(EventRecord.entity_reference.in_(entities)))]
    task_ids=select(WorkTask.id).where(WorkTask.case_id==case_id)
    task_events=[dict(row) for row in session.execute(select(TaskHistory.id,TaskHistory.task_id,TaskHistory.event_type,
        TaskHistory.attempt_number,TaskHistory.created_at,TaskHistory.details).where(TaskHistory.task_id.in_(task_ids))).mappings()]
    return dict(case_id=case_id, case_number=case.case_number, final_state=case.status.value,
        created_at=case.created_at, source_events=events,
        task_events=task_events,
        tasks=rows(WorkTask, ("id", "task_type", "status", "attempt_count", "created_at", "updated_at", "result")),
        investigations=rows(InvestigationRun, ("id", "task_id", "role", "status", "started_at", "completed_at", "result", "telemetry")),
        supervisor=rows(SupervisorReview, ("id", "outcome", "created_at", "result", "telemetry")),
        controls=controls,
        approvals=[dict(row) for row in session.execute(select(ActionApproval.id, ActionApproval.authorization_id,
            ActionApproval.status, ActionApproval.created_at).where(ActionApproval.authorization_id.in_(approval_ids))).mappings()],
        actions=rows(ActionRecord, ("id", "action_type", "status", "created_at")),
        operations=rows(ExecutionOperation, ("id", "action_id", "status", "event_id", "created_at", "completed_at")),
        verifications=rows(VerificationResult, ("id", "action_id", "success", "verification_type", "observed_state", "created_at", "detail")),
        evidence=rows(Evidence, ("id", "source_system", "source_record_id", "retrieval_timestamp", "integrity_metadata")),
        audit=rows(AuditLog, ("id", "event_type", "created_at", "details")))
