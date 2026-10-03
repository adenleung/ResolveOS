from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text
from app.intelligence.contracts import AnalyticsAccess
from app.intelligence.service import IntelligenceService, require_access
from app.reliability.contracts import ShadowRequest, ShadowResult, ReplayReport
from app.reliability.service import ShadowService
from app.reliability.replay import ReplayService
from app.reliability.models import ShadowEvaluation
from app.orchestration.auth import development_auth
from app.orchestration.models import WorkTask


def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}/reliability", tags=["Shadow and replay"])
    identify = development_auth(settings)
    def invoke(operation):
        try:
            return operation()
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/cases/{case_id}/shadow", response_model=ShadowResult)
    def shadow(case_id: str, request: ShadowRequest, identity=Depends(identify)):
        return invoke(lambda: ShadowService(database, settings).evaluate(case_id, request, AnalyticsAccess(identity)))

    @api.get("/cases/{case_id}/shadow", response_model=list[ShadowResult])
    def shadows(case_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        return invoke(lambda: ShadowService(database, settings).list(case_id, AnalyticsAccess(identity), limit, offset))

    @api.get("/cases/{case_id}/replay", response_model=ReplayReport)
    def replay(case_id: str, as_of: datetime | None = None, identity=Depends(identify)):
        def read():
            with database.get_session() as session:
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                return ReplayService(session, AnalyticsAccess(identity)).replay(case_id, as_of)
        return invoke(read)

    @api.get("/cases/{case_id}/shadow-comparison")
    def comparison(case_id: str, identity=Depends(identify)):
        return invoke(lambda: ShadowService(database, settings).comparison(case_id, AnalyticsAccess(identity)))

    @api.get("/telemetry")
    def telemetry(identity=Depends(identify)):
        def read():
            access = AnalyticsAccess(identity)
            require_access(access)
            with database.get_session() as session:
                session.execute(text("SET TRANSACTION READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                report = IntelligenceService(session, access).report()
                return {"queue_by_status": dict(session.execute(select(WorkTask.status, func.count()).group_by(WorkTask.status)).all()),
                        "retry_attempts": session.scalar(select(func.coalesce(func.sum(func.greatest(WorkTask.attempt_count - 1, 0)), 0))),
                        "shadow_count": session.scalar(select(func.count()).select_from(ShadowEvaluation)),
                        "current_cohort": report.overview, "measured_durations": [m.model_dump(mode="json") for m in report.bottlenecks],
                        "recurrences": [r.model_dump(mode="json") for r in report.recurrences], "cohort_truncated": report.truncated,
                        "replay_available": True, "ml_operational_enabled": False,
                        "limitation": "Queue/shadow counts are current global synthetic telemetry; duration/outcome observations use the bounded last-30-day cohort."}
        return invoke(read)
    return api
