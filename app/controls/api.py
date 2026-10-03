from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.controls.contracts import ActionRequest
from app.controls.models import ActionApproval, ActionApprovalHistory, ControlAuthorization
from app.controls.service import Controls
from app.orchestration.auth import development_auth

class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supervisor_review_id: str
    policy_version_id: str
    action: ActionRequest

class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    reason: str = Field(min_length=1, max_length=1000)

class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_id: str

def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}")
    identify = development_auth(settings)
    def invoke(operation):
        try:
            with database.get_session() as session:
                return operation(Controls(session, settings))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/cases/{case_id}/controls/evaluate")
    def evaluate(case_id: str, request: EvaluationRequest, identity=Depends(identify)):
        return invoke(lambda controls: controls.evaluate(case_id, request.supervisor_review_id,
            request.policy_version_id, request.action, identity))

    @api.get("/cases/{case_id}/authorizations")
    def records(case_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        def read(controls):
            controls.workflow.case(case_id)
            records = controls.session.execute(select(ControlAuthorization).where(ControlAuthorization.case_id == case_id)
                .order_by(ControlAuthorization.created_at.desc(), ControlAuthorization.id).offset(offset).limit(limit)).scalars().all()
            result = []
            for record in records:
                approval = controls.session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == record.id))
                result.append({**controls.serialize(record), "approval": {"id": approval.id, "status": approval.status,
                    "assigned_role": approval.assigned_role, "assigned_user": approval.assigned_user,
                    "expires_at": approval.expires_at} if approval else None})
            return result
        return invoke(read)

    @api.post("/action-approvals/{approval_id}/decision")
    def decision(approval_id: str, request: ApprovalRequest, identity=Depends(identify)):
        return invoke(lambda controls: controls.approve(approval_id, identity, request.operation, request.reason))

    @api.get("/action-approvals/{approval_id}/history")
    def history(approval_id: str, identity=Depends(identify)):
        def read(controls):
            if controls.session.get(ActionApproval, approval_id) is None:
                raise LookupError("action_approval_not_found")
            return [{"actor": row.actor, "operation": row.operation, "reason": row.reason,
                "created_at": row.created_at} for row in controls.session.execute(select(ActionApprovalHistory)
                    .where(ActionApprovalHistory.approval_id == approval_id).order_by(ActionApprovalHistory.created_at).limit(100)).scalars()]
        return invoke(read)

    @api.post("/actions/submit")
    def submit(request: ExecutionRequest, identity=Depends(identify)):
        from app.execution.service import ExecutionEngine
        return invoke(lambda controls: ExecutionEngine(controls.session, settings).submit(request.authorization_id, identity))

    @api.post("/authorizations/{authorization_id}/simulate")
    def simulate(authorization_id: str, identity=Depends(identify)):
        from app.execution.service import ExecutionEngine
        return invoke(lambda controls: ExecutionEngine(controls.session, settings).preview(authorization_id, identity))

    @api.get("/cases/{case_id}/simulations")
    def simulations(case_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        from app.execution.models import CounterfactualSimulation
        from app.execution.service import ExecutionEngine
        def read(controls):
            Controls.require(identity, "WORKER")
            controls.workflow.case(case_id)
            records = controls.session.scalars(select(CounterfactualSimulation).where(
                CounterfactualSimulation.case_id == case_id).order_by(
                CounterfactualSimulation.created_at.desc(), CounterfactualSimulation.id.desc())
                .offset(offset).limit(limit)).all()
            return [ExecutionEngine.serialize_simulation(row) for row in records]
        return invoke(read)

    @api.get("/cases/{case_id}/actions")
    def actions(case_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        from app.execution.models import ExecutionOperation
        from app.models.domain import VerificationResult
        def read(controls):
            controls.workflow.case(case_id)
            operations = controls.session.execute(select(ExecutionOperation).where(ExecutionOperation.case_id == case_id)
                .order_by(ExecutionOperation.created_at.desc()).offset(offset).limit(limit)).scalars().all()
            return [{"id": row.id, "action_id": row.action_id, "authorization_id": row.authorization_id,
                "status": row.status, "created_at": row.created_at, "completed_at": row.completed_at,
                "verification": [{"id": result.id, "success": result.success, "detail": result.detail,
                    "observed_state": result.observed_state} for result in controls.session.execute(select(VerificationResult)
                    .where(VerificationResult.action_id == row.action_id)).scalars()]} for row in operations]
        return invoke(read)
    return api
