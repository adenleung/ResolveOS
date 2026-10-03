from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from app.intelligence.contracts import AnalyticsAccess, IntelligenceReport, IncidentRelationships
from app.intelligence.service import IntelligenceService
from app.orchestration.auth import development_auth


def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}/intelligence", tags=["Operational intelligence"])
    identify = development_auth(settings)
    def invoke(identity, callback):
        try:
            with database.get_session() as session:
                session.execute(text("SET TRANSACTION READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                return callback(IntelligenceService(session, AnalyticsAccess(identity)))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @api.get("/report", response_model=IntelligenceReport)
    def report(start: datetime | None = None, end: datetime | None = None,
               case_limit: int = Query(500, ge=1, le=500), identity=Depends(identify)):
        return invoke(identity, lambda service: service.report(start, end, case_limit))

    @api.get("/incidents/{incident_id}/relationships", response_model=IncidentRelationships)
    def relationships(incident_id: str, identity=Depends(identify)):
        return invoke(identity, lambda service: service.relationships(incident_id))
    return api
