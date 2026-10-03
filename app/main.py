from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.classification.service import ClassificationService
from app.correlation.service import IncidentCorrelationService
from app.database import DatabaseManager
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import DetectionHistory, EventRecord, ExceptionEvidence, IngestionError
from app.ingestion.service import EventIngestionService
from app.logging_config import configure_logging
from app.models.domain import AuditLog, Case, ExceptionRecord, Incident
from app.simulator.service import SimulatorScenarioService
from app.orchestration.api import router as orchestration_router
from app.controls.api import router as controls_router
from app.memory.api import router as memory_router
from app.intelligence.api import router as intelligence_router

logger = logging.getLogger(__name__)


class ScenarioRequest(BaseModel):
    scenario_name: str
    seed: int | None = None


class AssessmentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class CorrelationRunRequest(BaseModel):
    after_case_id: str | None = None


class IncidentStatusRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=500)
    evidence_event_ids: list[str] = Field(default_factory=list)


class IncidentCaseRequest(BaseModel):
    case_id: str
    reason: str = Field(min_length=1, max_length=500)
    evidence_event_ids: list[str] = Field(min_length=1)


class IncidentSplitRequest(BaseModel):
    groups: list[list[str]] = Field(min_length=2)
    reason: str = Field(min_length=1, max_length=500)


class IncidentMergeRequest(BaseModel):
    source_incident_id: str
    reason: str = Field(min_length=1, max_length=500)
    evidence_event_ids: list[str] = Field(min_length=1)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = DatabaseManager(settings.database_url or "sqlite:///./resolveos.db", echo=settings.database_echo)

    def correlation_service(session):
        return IncidentCorrelationService(
            session,
            event_time_window=timedelta(seconds=settings.correlation_event_window_seconds),
            batch_size=settings.correlation_batch_size,
            candidate_limit=settings.correlation_candidate_limit,
            event_limit=settings.correlation_event_limit,
            candidate_pair_limit=settings.correlation_pair_limit,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            database.create_all()
            logger.info("Application startup complete")
        except Exception as exc:  # pragma: no cover - startup guard
            logger.exception("Startup failed: %s", exc)
            raise
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error for %s: %s", request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "internal_server_error"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/ready")
    async def readiness() -> dict[str, str | bool]:
        is_ready = database.check_connection()
        return {"status": "ready" if is_ready else "unavailable", "database_connected": is_ready}

    @app.get(f"{settings.api_prefix}/{settings.api_version}/health")
    async def versioned_health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": settings.app_version}

    @app.get(f"{settings.api_prefix}/{settings.api_version}/db/ready")
    async def versioned_readiness() -> dict[str, str | bool]:
        is_ready = database.check_connection()
        return {"status": "ready" if is_ready else "unavailable", "database_connected": is_ready}

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/scenarios")
    async def list_scenarios() -> dict[str, list[str]]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            return {"scenarios": service.list_scenarios()}

    @app.post(f"{settings.api_prefix}/{settings.api_version}/simulator/scenarios/generate")
    async def generate_scenario(payload: ScenarioRequest) -> dict[str, str]:
        try:
            with database.get_session() as session:
                service = SimulatorScenarioService(session)
                created = service.generate_scenario(payload.scenario_name, payload.seed)
                sanitized = {key: value for key, value in created.items() if key != "root_cause"}
                return sanitized
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/payments/{{payment_id}}")
    async def get_payment(payment_id: str) -> dict[str, str | None]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            payment = service.get_payment(payment_id)
            if payment is None:
                raise HTTPException(status_code=404, detail="payment_not_found")
            return {
                "payment_id": payment.payment_id,
                "idempotency_key": payment.idempotency_key,
                "status": payment.status,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "beneficiary": payment.beneficiary,
                "scenario_name": payment.scenario_name,
                "correlation_id": payment.correlation_id,
            }

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/payments/{{payment_id}}/ledger")
    async def get_payment_ledger(payment_id: str) -> list[dict[str, str]]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            ledger_rows = service.get_ledger_records(payment_id)
            return [
                {
                    "id": row.id,
                    "ledger_transaction_id": row.ledger_transaction_id,
                    "entry_type": row.entry_type,
                    "amount": str(row.amount),
                    "currency": row.currency,
                    "balance_after": str(row.balance_after),
                    "status": row.status,
                }
                for row in ledger_rows
            ]

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/payments/{{payment_id}}/confirmations")
    async def get_payment_confirmations(payment_id: str) -> list[dict[str, str | bool]]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            rows = service.get_confirmations(payment_id)
            return [
                {
                    "event_id": row.event_id,
                    "status": row.status,
                    "event_type": row.event_type,
                    "correlation_id": row.correlation_id,
                    "is_duplicate": row.is_duplicate,
                    "occurred_at": row.occurred_at.isoformat(),
                }
                for row in rows
            ]

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/logs")
    async def get_technology_logs(correlation_id: str | None = None, payment_id: str | None = None) -> list[dict[str, str | int | None]]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            rows = service.get_logs(correlation_id=correlation_id, payment_id=payment_id)
            return [
                {
                    "service_name": row.service_name,
                    "method": row.method,
                    "endpoint": row.endpoint,
                    "status_code": row.status_code,
                    "latency_ms": row.latency_ms,
                    "correlation_id": row.correlation_id,
                    "error_type": row.error_type,
                    "occurred_at": row.occurred_at.isoformat(),
                }
                for row in rows
            ]

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/workflows/{{workflow_id}}")
    async def get_workflow_state(workflow_id: str) -> dict[str, str | bool | list[str] | None]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            workflow = service.get_workflow(workflow_id)
            if workflow is None:
                raise HTTPException(status_code=404, detail="workflow_not_found")
            return {
                "workflow_id": workflow.workflow_id,
                "workflow_status": workflow.workflow_status,
                "current_step": workflow.current_step,
                "pending_tasks": workflow.pending_tasks or [],
                "approval_required": workflow.approval_required,
                "approval_status": workflow.approval_status,
                "last_updated_at": workflow.last_updated_at.isoformat(),
            }

    @app.get(f"{settings.api_prefix}/{settings.api_version}/simulator/policies")
    async def get_policies() -> list[dict[str, str | bool | None]]:
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            rows = service.get_policies()
            return [
                {
                    "policy_code": row.policy_code,
                    "version": row.version,
                    "name": row.name,
                    "approval_required": row.approval_required,
                    "effective_from": row.effective_from.isoformat(),
                    "effective_to": row.effective_to.isoformat() if row.effective_to else None,
                }
                for row in rows
            ]

    @app.delete(f"{settings.api_prefix}/{settings.api_version}/simulator/reset")
    async def reset_simulator() -> dict[str, str]:
        if settings.environment.lower() == "production":
            raise HTTPException(status_code=403, detail="reset_is_disabled_in_production")
        with database.get_session() as session:
            service = SimulatorScenarioService(session)
            service.reset_state()
        return {"status": "reset", "environment": settings.environment}

    @app.post(f"{settings.api_prefix}/{settings.api_version}/ingestion/synthetic")
    async def ingest_synthetic_events() -> dict:
        with database.get_session() as session:
            return EventIngestionService(session).ingest_synthetic()

    @app.get(f"{settings.api_prefix}/{settings.api_version}/ingestion/status")
    async def ingestion_status() -> dict:
        with database.get_session() as session:
            stats = EventIngestionService(session).status()
            stats["rejected_records"] = session.execute(select(func.count()).select_from(IngestionError)).scalar_one()
            return stats

    @app.post(f"{settings.api_prefix}/{settings.api_version}/detection/run")
    async def run_detection() -> dict:
        with database.get_session() as session:
            service = ExceptionDetectionService(
                session,
                confirmation_window=timedelta(seconds=settings.confirmation_window_seconds),
                workflow_deadline=timedelta(seconds=settings.workflow_deadline_seconds),
                api_timeout_ms=settings.api_timeout_ms,
            )
            return service.run()

    @app.get(f"{settings.api_prefix}/{settings.api_version}/exceptions")
    async def list_exceptions(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> list[dict]:
        with database.get_session() as session:
            rows = session.execute(
                select(ExceptionRecord, Case)
                .join(Case, ExceptionRecord.case_id == Case.id)
                .order_by(ExceptionRecord.detected_at.desc().nullslast(), ExceptionRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [
                {
                    "id": exception.id,
                    "case_id": exception.case_id,
                    "case_number": case.case_number,
                    "exception_type": exception.exception_type,
                    "description": exception.description,
                    "severity": exception.severity,
                    "condition_status": exception.condition_status,
                    "detection_key": exception.detection_key,
                    "detected_at": exception.detected_at.isoformat() if exception.detected_at else None,
                }
                for exception, case in rows
            ]

    @app.get(f"{settings.api_prefix}/{settings.api_version}/exceptions/{{exception_id}}")
    async def get_exception(exception_id: str) -> dict:
        with database.get_session() as session:
            exception = session.get(ExceptionRecord, exception_id)
            if exception is None:
                raise HTTPException(status_code=404, detail="exception_not_found")
            evidence_rows = session.execute(
                select(EventRecord)
                .join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
                .where(ExceptionEvidence.exception_id == exception.id)
                .order_by(EventRecord.occurred_at, EventRecord.ingested_at)
            ).scalars().all()
            history = session.execute(
                select(DetectionHistory)
                .where(DetectionHistory.exception_id == exception.id)
                .order_by(DetectionHistory.detected_at, DetectionHistory.id)
            ).scalars().all()
            return {
                "id": exception.id,
                "case_id": exception.case_id,
                "exception_type": exception.exception_type,
                "description": exception.description,
                "severity": exception.severity,
                "condition_status": exception.condition_status,
                "detected_at": exception.detected_at.isoformat() if exception.detected_at else None,
                "evidence": [
                    {
                        "event_record_id": event.id,
                        "event_id": event.event_id,
                        "source_system": event.source_system,
                        "event_type": event.event_type,
                        "entity_reference": event.entity_reference,
                        "correlation_id": event.correlation_id,
                        "occurred_at": event.occurred_at.isoformat(),
                        "ingested_at": event.ingested_at.isoformat(),
                        "source_record_reference": event.source_record_reference,
                        "payload": event.payload,
                    }
                    for event in evidence_rows
                ],
                "history": [
                    {
                        "event_type": item.event_type,
                        "summary": item.summary,
                        "detected_at": item.detected_at.isoformat(),
                        "event_occurred_at": item.event_occurred_at.isoformat() if item.event_occurred_at else None,
                        "details": item.details,
                    }
                    for item in history
                ],
            }

    @app.get(f"{settings.api_prefix}/{settings.api_version}/detection/stats")
    async def detection_stats() -> dict:
        with database.get_session() as session:
            counts = session.execute(
                select(ExceptionRecord.exception_type, func.count()).group_by(ExceptionRecord.exception_type)
            ).all()
            return {
                "ingestion": EventIngestionService(session).status(),
                "exceptions_total": session.execute(select(func.count()).select_from(ExceptionRecord)).scalar_one(),
                "exceptions_by_type": {exception_type: count for exception_type, count in counts},
                "detection_history_entries": session.execute(select(func.count()).select_from(DetectionHistory)).scalar_one(),
                "audit_entries": session.execute(
                    select(func.count()).select_from(AuditLog).where(AuditLog.event_type.in_(["exception_detected", "exception_evidence_updated"]))
                ).scalar_one(),
            }

    @app.post(f"{settings.api_prefix}/{settings.api_version}/exceptions/{{exception_id}}/classify")
    @app.post(f"{settings.api_prefix}/{settings.api_version}/exceptions/{{exception_id}}/classify/re-evaluate")
    async def classify_exception(exception_id: str, payload: AssessmentRequest | None = None) -> dict:
        try:
            with database.get_session() as session:
                service = ClassificationService(
                    session,
                    confirmation_window=timedelta(seconds=settings.confirmation_window_seconds),
                    workflow_deadline=timedelta(seconds=settings.workflow_deadline_seconds),
                )
                return service.evaluate(exception_id, reason=payload.reason if payload else None)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(f"{settings.api_prefix}/{settings.api_version}/exceptions/{{exception_id}}/classification")
    async def get_exception_classification(exception_id: str) -> dict:
        with database.get_session() as session:
            if session.get(ExceptionRecord, exception_id) is None:
                raise HTTPException(status_code=404, detail="exception_not_found")
            service = ClassificationService(session)
            result = service.get_exception_assessment(exception_id)
            if result is None:
                raise HTTPException(status_code=404, detail="classification_not_found")
            return {"assessment": result, "history": service.get_history(exception_id)}

    @app.get(f"{settings.api_prefix}/{settings.api_version}/cases/{{case_id}}/priority")
    async def get_case_priority(case_id: str) -> dict:
        with database.get_session() as session:
            case = session.get(Case, case_id)
            if case is None:
                raise HTTPException(status_code=404, detail="case_not_found")
            assessment = ClassificationService(session).get_case_assessment(case_id)
            return {
                "case_id": case.id,
                "priority": case.priority,
                "sla_started_at": case.sla_started_at.isoformat() if case.sla_started_at else None,
                "sla_deadline": case.sla_deadline.isoformat() if case.sla_deadline else None,
                "sla_rule_version": case.sla_rule_version,
                "sla": assessment["sla"] if assessment else None,
                "priority_assessment": assessment["priority"] if assessment else None,
            }

    @app.get(f"{settings.api_prefix}/{settings.api_version}/cases/{{case_id}}/routing")
    async def get_case_routing(case_id: str) -> dict:
        with database.get_session() as session:
            if session.get(Case, case_id) is None:
                raise HTTPException(status_code=404, detail="case_not_found")
            assessment = ClassificationService(session).get_case_assessment(case_id)
            if assessment is None:
                return {
                    "recommended_specialists": [],
                    "fallback_queue": "HUMAN_TRIAGE",
                    "human_triage_required": True,
                    "rule_version": "specialist-routing-1.0",
                    "applied_rules": [],
                }
            return assessment["routing"]

    @app.post(f"{settings.api_prefix}/{settings.api_version}/incidents/correlate")
    async def correlate_incidents(payload: CorrelationRunRequest | None = None) -> dict:
        with database.get_session() as session:
            service = correlation_service(session)
            return service.run(after_case_id=payload.after_case_id if payload else None)

    @app.get(f"{settings.api_prefix}/{settings.api_version}/incidents")
    async def list_incidents(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict]:
        with database.get_session() as session:
            return correlation_service(session).list_incidents(status=status, limit=limit, offset=offset)

    @app.get(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}")
    async def get_incident(incident_id: str) -> dict:
        with database.get_session() as session:
            result = correlation_service(session).incident_summary(incident_id)
            if result is None:
                raise HTTPException(status_code=404, detail="incident_not_found")
            return result

    @app.get(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/cases")
    async def get_incident_cases(incident_id: str) -> list[dict]:
        with database.get_session() as session:
            result = correlation_service(session).incident_summary(incident_id)
            if result is None:
                raise HTTPException(status_code=404, detail="incident_not_found")
            return result["cases"]

    @app.get(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/evidence")
    async def get_incident_evidence(incident_id: str) -> list[dict]:
        with database.get_session() as session:
            result = correlation_service(session).incident_evidence(incident_id)
            if result is None:
                raise HTTPException(status_code=404, detail="incident_not_found")
            return result

    @app.get(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/history")
    async def get_incident_history(incident_id: str) -> list[dict]:
        with database.get_session() as session:
            if session.get(Incident, incident_id) is None:
                raise HTTPException(status_code=404, detail="incident_not_found")
            return correlation_service(session).incident_history(incident_id)

    @app.post(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/re-evaluate")
    async def reevaluate_incident(incident_id: str) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).reevaluate_incident(incident_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/status")
    async def change_incident_status(incident_id: str, payload: IncidentStatusRequest) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).transition_status(
                    incident_id, payload.status, payload.reason, payload.evidence_event_ids
                )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/cases")
    async def add_incident_case(incident_id: str, payload: IncidentCaseRequest) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).add_case(
                    incident_id, payload.case_id, payload.reason, payload.evidence_event_ids
                )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/cases/{{case_id}}")
    async def remove_incident_case(incident_id: str, case_id: str, reason: str = Query(min_length=1, max_length=500)) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).remove_case(incident_id, case_id, reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/split")
    async def split_incident(incident_id: str, payload: IncidentSplitRequest) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).split_incident(incident_id, payload.groups, payload.reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(f"{settings.api_prefix}/{settings.api_version}/incidents/{{incident_id}}/merge")
    async def merge_incident(incident_id: str, payload: IncidentMergeRequest) -> dict:
        try:
            with database.get_session() as session:
                return correlation_service(session).merge_incidents(
                    incident_id,
                    payload.source_incident_id,
                    payload.reason,
                    payload.evidence_event_ids,
                )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    app.include_router(orchestration_router(database, settings))
    app.include_router(controls_router(database, settings))
    app.include_router(memory_router(database, settings))
    app.include_router(intelligence_router(database, settings))
    return app


app = create_app()
