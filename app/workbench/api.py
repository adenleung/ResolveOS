from datetime import datetime
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, text, or_

from app.domain.case_service import CaseState
from app.models.domain import Case, ExceptionRecord, Evidence, CaseIncident, PolicyVersion
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.classification.models import AssessmentHistory
from app.investigation.tools import clean_payload
from app.orchestration.auth import development_auth
from app.orchestration.models import WorkflowReview, TaskConsumer
from app.orchestration.service import OrchestrationService
from app.controls.models import ActionApproval, ControlAuthorization
from app.controls.service import Controls
from app.execution.models import CounterfactualSimulation
from app.execution.service import ExecutionEngine
from app.memory.models import MemoryVersion, OperationalMemory
from app.memory.service import MemoryService
from app.memory.contracts import MemoryAccess, LABEL
from app.supervisor.models import SupervisorReview
from app.investigation.models import InvestigationRun


class CaseSummary(BaseModel):
    id: str
    case_number: str
    status: str
    summary: str | None
    priority: str
    created_at: datetime
    updated_at: datetime
    sla_deadline: datetime | None
    categories: list[str]
    incident_ids: list[str]


class CasePage(BaseModel):
    items: list[CaseSummary]
    total: int
    limit: int
    offset: int


class CaseDetail(BaseModel):
    case: CaseSummary
    exceptions: list[dict[str, Any]]
    assessments: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    investigations: list[dict[str, Any]]
    supervisor_reviews: list[dict[str, Any]]
    authorizations: list[dict[str, Any]]
    simulations: list[dict[str, Any]]
    tasks: dict[str, Any]
    policies: list[dict[str, Any]]
    truncated: bool


def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}/workbench", tags=["Employee workbench"])
    identify = development_auth(settings)

    def read(operation):
        try:
            with database.get_session() as session:
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                return operation(session)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    def summary(session, case):
        assessment = session.scalar(select(AssessmentHistory).where(AssessmentHistory.case_id == case.id)
            .order_by(AssessmentHistory.created_at.desc(), AssessmentHistory.id).limit(1))
        categories = sorted({r["category"] for r in (assessment.assessment.get("classification", {}).get("categories", []) if assessment else [])})
        incidents = list(session.scalars(select(CaseIncident.incident_id).where(CaseIncident.case_id == case.id, CaseIncident.removed_at.is_(None))))
        return CaseSummary(**{key: getattr(case, key) for key in ("id", "case_number", "summary", "priority", "created_at", "updated_at", "sla_deadline")},
            status=case.status.value, categories=categories, incident_ids=incidents)

    def authorization(session, row):
        approval = session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == row.id))
        policy = session.get(PolicyVersion, row.policy_version_id) if row.policy_version_id else None
        simulations = session.scalars(select(CounterfactualSimulation).where(CounterfactualSimulation.authorization_id == row.id)
            .order_by(CounterfactualSimulation.created_at.desc()).limit(10)).all()
        return {**Controls.serialize(row), "control_snapshot": row.snapshot,
            "policy": {key:getattr(policy,key) for key in ("id", "version", "is_active", "effective_from", "content")} if policy else None,
            "counterfactual_reports": [ExecutionEngine.serialize_simulation(item) for item in simulations],
            "approval": {key: getattr(approval, key) for key in
            ("id", "status", "assigned_role", "assigned_user", "expires_at")} if approval else None}

    @api.get("/identity")
    def identity(current=Depends(identify)):
        return {"user_id": current.user_id, "roles": sorted(current.roles), "environment": settings.environment,
                "synthetic_only": True, "live_provider_enabled": settings.investigator_live_enabled}

    @api.get("/cases", response_model=CasePage)
    def cases(q: str = Query("", max_length=100), status: CaseState | None = None,
              priority: str | None = Query(None, max_length=20), limit: int = Query(25, ge=1, le=50),
              offset: int = Query(0, ge=0), current=Depends(identify)):
        def query(session):
            statement = select(Case)
            if q.strip():
                term = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                statement = statement.where(or_(Case.case_number.ilike(term, escape="\\"), Case.summary.ilike(term, escape="\\")))
            if status: statement = statement.where(Case.status == status)
            if priority: statement = statement.where(Case.priority == priority.upper())
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.order_by(Case.created_at.desc(), Case.id).limit(limit).offset(offset)).all()
            return CasePage(items=[summary(session, row) for row in rows], total=total, limit=limit, offset=offset)
        return read(query)

    @api.get("/cases/{case_id}", response_model=CaseDetail)
    def detail(case_id: str, current=Depends(identify)):
        def query(session):
            case = session.get(Case, case_id)
            if case is None: raise LookupError("case_not_found")
            capped = False
            def rows(statement):
                nonlocal capped
                result = session.scalars(statement.limit(101)).all()
                capped |= len(result) > 100
                return result[:100]
            exceptions = rows(select(ExceptionRecord).where(ExceptionRecord.case_id == case_id).order_by(ExceptionRecord.id))
            assessments = rows(select(AssessmentHistory).where(AssessmentHistory.case_id == case_id).order_by(AssessmentHistory.created_at.desc(), AssessmentHistory.id))
            event_ids = select(ExceptionEvidence.event_record_id).join(ExceptionRecord,
                ExceptionRecord.id == ExceptionEvidence.exception_id).where(ExceptionRecord.case_id == case_id)
            event_query = select(EventRecord).where(EventRecord.id.in_(event_ids)).order_by(EventRecord.occurred_at, EventRecord.id)
            events = [{"id": row.id, "kind": "NORMALIZED_SOURCE", "source_system": row.source_system, "source_record_id": row.source_record_reference,
                "occurred_at": row.occurred_at, "available_at": row.ingested_at, "payload": clean_payload(row.payload)} for row in rows(event_query)]
            events.extend({"id": row.id, "kind": "RETRIEVED_EVIDENCE", "source_system": row.source_system, "source_record_id": row.source_record_id,
                "occurred_at": row.relevant_event_timestamp, "available_at": row.retrieval_timestamp, "payload": clean_payload(row.payload),
                "event_record_id": (row.integrity_metadata or {}).get("event_record_id")} for row in rows(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.retrieval_timestamp, Evidence.id)))
            service = OrchestrationService(session, settings)
            related = select(TaskConsumer.task_id).where(TaskConsumer.case_id == case_id)
            runs = rows(select(InvestigationRun).where(or_(InvestigationRun.case_id == case_id, InvestigationRun.task_id.in_(related)))
                .order_by(InvestigationRun.started_at.desc(), InvestigationRun.id))
            reviews = rows(select(SupervisorReview).where(SupervisorReview.case_id == case_id).order_by(SupervisorReview.created_at.desc(), SupervisorReview.id))
            task_data = service.task_history(case_id, 100, 0)
            capped |= len(task_data["tasks"]) >= 100 or len(task_data["events"]) >= 5000
            return CaseDetail(case=summary(session, case), exceptions=[{key:getattr(row,key) for key in
                ("id", "exception_type", "description", "severity", "source_reference", "detected_at", "condition_status")} for row in exceptions],
                assessments=[{"id": row.id, "created_at": row.created_at, "classification_source": row.classification_source,
                    "assessment": row.assessment} for row in assessments], evidence=events,
                investigations=[{key:getattr(row,key) for key in ("id", "role", "status", "attempt", "model", "started_at", "completed_at", "result", "error_code")} for row in runs],
                supervisor_reviews=[{key:getattr(row,key) for key in ("id", "outcome", "model", "created_at", "result")} for row in reviews],
                authorizations=[authorization(session, row) for row in rows(select(ControlAuthorization).where(ControlAuthorization.case_id == case_id).order_by(ControlAuthorization.created_at.desc()))],
                simulations=[ExecutionEngine.serialize_simulation(row) for row in rows(select(CounterfactualSimulation).where(CounterfactualSimulation.case_id == case_id).order_by(CounterfactualSimulation.created_at.desc()))],
                tasks=task_data,
                policies=[{key:getattr(row,key) for key in ("id", "version", "is_active", "effective_from", "content")} for row in rows(select(PolicyVersion).order_by(PolicyVersion.effective_from.desc(), PolicyVersion.id))],
                truncated=capped)
        return read(query)

    @api.get("/approvals")
    def approvals(status: str = Query("OPEN", max_length=30), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), current=Depends(identify)):
        if "OPERATIONS_REVIEWER" not in current.roles: raise HTTPException(403, "reviewer_permission_required")
        def query(session):
            action_query = select(ActionApproval, ControlAuthorization).join(ControlAuthorization, ControlAuthorization.id == ActionApproval.authorization_id).where(
                ActionApproval.assigned_role.in_(current.roles), or_(ActionApproval.assigned_user.is_(None), ActionApproval.assigned_user == current.user_id))
            workflow_query = select(WorkflowReview).where(WorkflowReview.assigned_role.in_(current.roles),
                or_(WorkflowReview.assigned_reviewer.is_(None), WorkflowReview.assigned_reviewer == current.user_id))
            if status != "ALL":
                action_query = action_query.where(ActionApproval.status == status)
                workflow_query = workflow_query.where(WorkflowReview.status == status)
            actions = session.execute(action_query.order_by(ActionApproval.created_at, ActionApproval.id).limit(limit).offset(offset)).all()
            workflows = session.scalars(workflow_query.order_by(WorkflowReview.deadline, WorkflowReview.id).limit(limit).offset(offset)).all()
            return {"actions": [{"kind": "ACTION_BOUND", "case_id": auth.case_id, "authorization": authorization(session, auth),
                "approval": {key:getattr(row,key) for key in ("id", "status", "assigned_role", "assigned_user", "expires_at")}} for row, auth in actions],
                "workflows": [{"kind": "WORKFLOW_ONLY", **{key:getattr(row,key) for key in ("id", "case_id", "status", "reason", "assigned_role", "assigned_reviewer", "deadline", "evidence_references")}} for row in workflows],
                "limit_per_kind": limit, "offset": offset}
        return read(query)

    @api.get("/memories")
    def memories(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), current=Depends(identify)):
        if "OPERATIONS_REVIEWER" not in current.roles: raise HTTPException(403, "reviewer_permission_required")
        def query(session):
            service, access = MemoryService(session, settings), MemoryAccess(current)
            records = session.execute(select(MemoryVersion, OperationalMemory.case_id).join(OperationalMemory, OperationalMemory.id == MemoryVersion.memory_id)
                .order_by(MemoryVersion.created_at.desc(), MemoryVersion.id).limit(limit).offset(offset)).all()
            result = []
            for version, case_id in records:
                service.require_version_sources(version, access)
                valid = False
                if version.status == "ACTIVE":
                    try: service.valid(version, service.case(case_id), access); valid = True
                    except ValueError: pass
                result.append({**service.serialize(version), "case_id": case_id, "currently_valid_historical_memory": valid})
            return {"items": result, "label": LABEL, "limit": limit, "offset": offset, "action_authorization": "NOT_EVALUATED"}
        return read(query)

    @api.get("/model-lab")
    def models(current=Depends(identify)):
        root = Path(__file__).resolve().parents[2]
        return {"operational_model_enabled": False, "runtime_authority": "DETERMINISTIC_CONTROLS",
            "checkpoint": "Phase 12 historical offline evaluation; not a current database readiness audit",
            "dataset_readiness": json.loads((root / "phase12-dataset-readiness.json").read_text()),
            "model_comparison": json.loads((root / "phase12-model-comparison.json").read_text()),
            "limitation": "No model trained or promoted. Native estimator execution was blocked by Windows Application Control. Metrics absent from the artifact remain unavailable."}
    return api
