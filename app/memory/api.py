from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.memory.contracts import CandidateRequest, MemoryAccess, ReviewRequest
from app.memory.models import MemoryReview, MemoryVersion, OperationalMemory
from app.memory.service import MemoryService
from app.orchestration.auth import development_auth


def router(database, settings):
    api = APIRouter(prefix=f"{settings.api_prefix}/{settings.api_version}")
    identify = development_auth(settings)

    def invoke(identity, operation):
        try:
            with database.get_session() as session:
                result = operation(MemoryService(session, settings), MemoryAccess(identity))
                session.commit()
                return result
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/cases/{case_id}/memory/candidates")
    def candidate(case_id: str, request: CandidateRequest, identity=Depends(identify)):
        return invoke(identity, lambda service, access: service.candidate(case_id, request, access))

    @api.post("/memory/versions/{version_id}/review")
    def review(version_id: str, request: ReviewRequest, identity=Depends(identify)):
        return invoke(identity, lambda service, access: service.review(version_id, request, access))

    @api.post("/memory/versions/{version_id}/reconcile")
    def reconcile(version_id: str, identity=Depends(identify)):
        return invoke(identity, lambda service, access: service.reconcile(version_id, access))

    @api.get("/cases/{case_id}/memory")
    def versions(case_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        def read(service, access):
            service.require(access, case_id, review=True)
            service.case(case_id)
            rows = service.session.scalars(select(MemoryVersion).join(OperationalMemory,
                OperationalMemory.id == MemoryVersion.memory_id).where(OperationalMemory.case_id == case_id)
                .order_by(MemoryVersion.created_at.desc(), MemoryVersion.id).limit(limit).offset(offset)).all()
            for row in rows:
                service.evidence(case_id, row.trust_snapshot["evidence_ids"], access)
            return [service.serialize(row) for row in rows]
        return invoke(identity, read)

    @api.get("/memory/versions/{version_id}/history")
    def history(version_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), identity=Depends(identify)):
        def read(service, access):
            version = service.session.get(MemoryVersion, version_id)
            if version is None:
                raise LookupError("memory_version_not_found")
            memory = service.session.get(OperationalMemory, version.memory_id)
            service.require(access, memory.case_id, review=True)
            service.require_version_sources(version, access)
            return [{key: getattr(row, key) for key in ("actor", "operation", "reason", "previous_status",
                "new_status", "replacement_id", "created_at")} for row in service.session.scalars(
                select(MemoryReview).where(MemoryReview.version_id == version_id)
                .order_by(MemoryReview.created_at, MemoryReview.id).limit(limit).offset(offset))]
        return invoke(identity, read)

    @api.get("/cases/{case_id}/memory/retrieve")
    def retrieve(case_id: str, category: str = Query(min_length=1, max_length=200),
                 top_k: int = Query(5, ge=1, le=10), context_bytes: int = Query(8000, ge=512, le=16000), identity=Depends(identify)):
        return invoke(identity, lambda service, access: service.retrieve(case_id, category, access,
            top_k=top_k, context_bytes=context_bytes))
    return api
