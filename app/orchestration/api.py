from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.orchestration.auth import development_auth
from app.orchestration.models import ReviewHistory, WorkflowReview
from app.orchestration.queue import utc
from app.orchestration.service import OrchestrationService
from sqlalchemy import select


class ClaimRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=1, ge=1, le=100)


class LeaseRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    lease_token: str = Field(min_length=1, max_length=100)


class RequeueRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    max_attempts: int = Field(ge=1, le=10)


class FailureRequest(LeaseRequest):
    error_code: str = Field(min_length=1, max_length=100, pattern="^[A-Za-z0-9_]+$")
    transient: bool = False


class ReviewDecision(BaseModel):
    decision: str
    reason: str = Field(min_length=1, max_length=500)


def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}")
    identify = development_auth(settings)

    def worker(identity=Depends(identify)):
        if "WORKER" not in identity.roles:
            raise HTTPException(403, "worker_permission_required")
        return identity

    def reviewer(identity=Depends(identify)):
        if "OPERATIONS_REVIEWER" not in identity.roles:
            raise HTTPException(403, "reviewer_permission_required")
        return identity

    def invoke(operation):
        try:
            with database.get_session() as session:
                return operation(OrchestrationService(session, settings))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.get("/cases/{case_id}/orchestration")
    def case_status(case_id: str, identity=Depends(identify)):
        return invoke(lambda service: service.status(case_id))

    @api.get("/cases/{case_id}/tasks")
    def case_tasks(case_id: str, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        return invoke(lambda service: service.task_history(case_id, limit, offset))

    @api.post("/cases/{case_id}/orchestrate")
    def schedule(case_id: str, reevaluate: bool = False, identity=Depends(worker)):
        return invoke(lambda service: service.schedule_case(case_id, reevaluate=reevaluate))

    @api.post("/orchestration/poll")
    def poll(after_case_id: str | None = None, identity=Depends(worker)):
        return invoke(lambda service: service.poll_cases(after_case_id))

    @api.get("/orchestration/stats")
    @api.get("/orchestration/health")
    def stats(identity=Depends(identify)):
        return invoke(lambda service: service.stats())

    @api.post("/orchestration/maintenance")
    def maintenance(identity=Depends(worker)):
        return invoke(lambda service: service.maintenance())

    @api.post("/orchestration/worker/claim")
    def claim(payload: ClaimRequest, identity=Depends(worker)):
        def run(service):
            result = service.queue.claim(payload.owner, payload.limit)
            service.session.commit()
            return result
        return invoke(run)

    @api.post("/orchestration/tasks/{task_id}/renew")
    def renew(task_id: str, payload: LeaseRequest, identity=Depends(worker)):
        def run(service):
            result = service.queue.renew(task_id, payload.owner, payload.lease_token)
            service.session.commit()
            return result
        return invoke(run)

    @api.post("/orchestration/tasks/{task_id}/run")
    def execute(task_id: str, payload: LeaseRequest, identity=Depends(worker)):
        from app.investigation.contracts import HANDLERS
        from app.investigation.provider import OpenAIProvider, ProviderError
        from app.investigation.service import InvestigationRunner
        from app.orchestration.models import WorkTask
        from app.orchestration.queue import LeaseLost
        with database.get_session() as session:
            task = session.get(WorkTask, task_id)
            if task is None:
                raise HTTPException(404, "task_not_found")
            investigation = task.task_type in HANDLERS
            supervisor = task.task_type == "REQUEST_SUPERVISOR_REVIEW"
            execution = task.task_type in {"PREPARE_EXECUTION", "REQUEST_VERIFICATION"} and task.payload.get("authorization_id") and task.payload.get("action_id")
        if execution:
            from app.execution.service import ExecutionEngine
            try:
                with database.get_session() as session:
                    return ExecutionEngine(session, settings).execute(task_id, payload.owner, payload.lease_token)
            except (ValueError, LeaseLost) as exc:
                raise HTTPException(409, str(exc)) from None
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from None
        if supervisor:
            from app.supervisor.service import SupervisorRunner
            from app.investigation.contracts import SupervisorOutput
            try:
                return SupervisorRunner(database, settings, OpenAIProvider(settings, output_model=SupervisorOutput)).run(
                    task_id, payload.owner, payload.lease_token)
            except ProviderError as exc:
                raise HTTPException(503, str(exc)) from None
            except LeaseLost:
                raise HTTPException(409, "task_lease_lost") from None
        if investigation:
            try:
                provider = OpenAIProvider(settings)
                return InvestigationRunner(database, settings, provider).run(task_id, payload.owner, payload.lease_token)
            except ProviderError as exc:
                raise HTTPException(503, str(exc)) from None
            except LeaseLost:
                raise HTTPException(409, "task_lease_lost") from None
        return invoke(lambda service: service.execute(task_id, payload.owner, payload.lease_token))

    @api.get("/cases/{case_id}/supervisor-reviews")
    def supervisor_reviews(case_id: str, limit: int = Query(50, ge=1, le=100),
                           offset: int = Query(0, ge=0), identity=Depends(identify)):
        from app.supervisor.models import SupervisorReview
        def read(service):
            service.case(case_id)
            rows = service.session.execute(select(SupervisorReview).where(SupervisorReview.case_id == case_id)
                .order_by(SupervisorReview.created_at.desc(), SupervisorReview.id).offset(offset).limit(limit)).scalars().all()
            return [{"id": row.id, "task_id": row.task_id, "attempt": row.attempt,
                "outcome": row.outcome, "model": row.model, "prompt_version": row.prompt_version,
                "created_at": row.created_at, "result": row.result, "telemetry": row.telemetry} for row in rows]
        return invoke(read)

    @api.get("/cases/{case_id}/investigations")
    def investigations(case_id: str, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0), identity=Depends(identify)):
        from app.investigation.models import InvestigationRun
        def read(service):
            service.case(case_id)
            from app.orchestration.models import TaskConsumer
            related = select(TaskConsumer.task_id).where(TaskConsumer.case_id == case_id)
            runs = service.session.execute(select(InvestigationRun).where(InvestigationRun.task_id.in_(related))
                .order_by(InvestigationRun.started_at.desc(), InvestigationRun.id).offset(offset).limit(limit)).scalars().all()
            return [{"id": run.id, "task_id": run.task_id, "role": run.role, "attempt": run.attempt,
                "status": run.status, "model": run.model, "prompt_version": run.prompt_version,
                "started_at": run.started_at, "completed_at": run.completed_at,
                "result": run.result, "telemetry": run.telemetry, "error_code": run.error_code} for run in runs]
        return invoke(read)

    @api.get("/cases/{case_id}/investigation-evidence")
    def investigation_evidence(case_id: str, limit: int = Query(100, ge=1, le=200),
                               offset: int = Query(0, ge=0), identity=Depends(identify)):
        from app.investigation.models import InvestigationRun
        from app.models.domain import Evidence
        from app.orchestration.models import TaskConsumer
        def read(service):
            service.case(case_id)
            # Shared evidence is visible only through this case's actual task consumers.
            runs = service.session.execute(select(InvestigationRun).where(InvestigationRun.task_id.in_(
                select(TaskConsumer.task_id).where(TaskConsumer.case_id == case_id)))
                .order_by(InvestigationRun.started_at.desc()).limit(100)).scalars().all()
            ids = {ref["evidence_id"] for run in runs for ref in (run.result or {}).get("evidence_references", [])}
            rows = service.session.execute(select(Evidence).where(Evidence.id.in_(ids))
                .order_by(Evidence.id).offset(offset).limit(limit)).scalars().all()
            return [{"id": row.id, "owner_case_id": row.case_id, "source_system": row.source_system,
                "source_record_id": row.source_record_id, "relevant_event_timestamp": row.relevant_event_timestamp,
                "retrieval_timestamp": row.retrieval_timestamp, "payload": row.payload,
                "integrity_metadata": row.integrity_metadata} for row in rows]
        return invoke(read)

    @api.get("/investigations/stats")
    def investigation_stats(identity=Depends(identify)):
        from app.investigation.models import InvestigationRun
        from sqlalchemy import func
        def read(service):
            return {"attempts_by_status": dict(service.session.execute(select(InvestigationRun.status,
                func.count()).group_by(InvestigationRun.status)).all()),
                "live_provider_enabled": settings.investigator_live_enabled}
        return invoke(read)

    @api.post("/orchestration/tasks/{task_id}/requeue")
    def requeue(task_id: str, payload: RequeueRequest, identity=Depends(worker)):
        def run(service):
            result = service.queue.requeue(task_id, payload.reason, payload.max_attempts)
            service.session.commit()
            return result
        return invoke(run)

    @api.post("/orchestration/tasks/{task_id}/fail")
    def fail(task_id: str, payload: FailureRequest, identity=Depends(worker)):
        def run(service):
            result = service.queue.fail(task_id, payload.owner, payload.lease_token, payload.error_code, payload.transient)
            service.session.commit()
            from app.execution.service import ExecutionEngine
            ExecutionEngine(service.session, settings).reconcile_terminal()
            return result
        return invoke(run)

    @api.get("/reviews")
    def reviews(status: str = "OPEN", limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(reviewer)):
        def read(service):
            rows = service.session.execute(select(WorkflowReview).where(WorkflowReview.status == status,
                WorkflowReview.assigned_role.in_(identity.roles)).order_by(WorkflowReview.deadline, WorkflowReview.id)
                .limit(limit).offset(offset)).scalars().all()
            return [{"id": item.id, "case_id": item.case_id, "status": item.status, "reason": item.reason,
                "assigned_role": item.assigned_role, "assigned_reviewer": item.assigned_reviewer,
                "evidence_references": item.evidence_references, "assessment_ids": item.assessment_ids,
                "deadline": utc(item.deadline).isoformat(), "approval_scope": "WORKFLOW_ONLY"} for item in rows
                if item.assigned_reviewer in {None, identity.user_id}]
        return invoke(read)

    @api.get("/reviews/{review_id}/history")
    def history(review_id: str, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(reviewer)):
        def read(service):
            review = service.session.get(WorkflowReview, review_id)
            if review is None:
                raise LookupError("review_not_found")
            if review.assigned_role not in identity.roles or review.assigned_reviewer not in {None, identity.user_id}:
                raise PermissionError("review_permission_denied")
            rows = service.session.execute(select(ReviewHistory).where(ReviewHistory.review_id == review_id)
                .order_by(ReviewHistory.created_at, ReviewHistory.id).limit(limit).offset(offset)).scalars().all()
            return [{"actor": item.actor, "operation": item.operation, "reason": item.reason,
                "details": item.details, "created_at": utc(item.created_at).isoformat()} for item in rows]
        return invoke(read)

    @api.post("/reviews/{review_id}/decision")
    def decision(review_id: str, payload: ReviewDecision, identity=Depends(reviewer)):
        return invoke(lambda service: service.decide_review(review_id, identity, payload.decision, payload.reason))

    @api.post("/reviews/{review_id}/assign")
    def assign(review_id: str, identity=Depends(reviewer)):
        return invoke(lambda service: service.assign_review(review_id, identity))

    return api
