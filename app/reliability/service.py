from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert
from uuid import uuid4
from app.controls.service import Controls
from app.intelligence.service import require_access
from app.reliability.models import ShadowEvaluation
from app.reliability.contracts import ShadowResult
from app.classification.models import AssessmentHistory
from app.models.domain import Case, VerificationResult
from app.models.domain import ActionRecord
from app.execution.models import ExecutionOperation
from app.orchestration.queue import digest, utc


class ShadowService:
    def __init__(self, database, settings):
        self.database, self.settings = database, settings

    def evaluate(self, case_id, request, access):
        require_access(access, case_id)
        # PostgreSQL enforces read-only inspection, including protection against
        # accidental future writes within the shared control calculation.
        with self.database.get_session() as session:
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            case, review, version, rules, action, snapshot, issues, outcome = Controls(session, self.settings, read_only=True).inspect(
                case_id, request.supervisor_review_id, request.policy_version_id, request.action, access.identity)
            routing = session.scalars(select(AssessmentHistory).where(AssessmentHistory.id.in_(snapshot["assessment_ids"])).limit(100)).all()
            observed_at = utc(session.scalar(select(func.clock_timestamp())))
            result = {"version": "shadow-controls-1.0", "snapshot": snapshot, "reasons": sorted(set(issues)),
                      "proposed_investigations": sorted({role for a in routing for role in a.assessment.get("routing", {}).get("recommended_specialists", [])}),
                      "recorded_supervisor_recommendation": review.result.get("proposed_action"),
                      "limitation": "Hypothetical control decision at observation time, not authorization or proof of successful remediation."}
        mapped = {"AUTO_ELIGIBLE": "WOULD_AUTO_ELIGIBLE", "HUMAN_APPROVAL_REQUIRED": "WOULD_HUMAN_APPROVAL_REQUIRED", "BLOCKED": "WOULD_BLOCK", "ESCALATED": "WOULD_ESCALATE"}[outcome]
        fingerprint = digest([case_id, access.identity.user_id, result, mapped])
        with self.database.get_session() as session:
            values = dict(id="shadow-" + uuid4().hex, case_id=case_id, actor=access.identity.user_id,
                          mode="SHADOW", action_authorization="NOT_EVALUATED", execution_permitted=False,
                          fingerprint=fingerprint, outcome=mapped, result=result, created_at=observed_at)
            row_id = session.scalar(insert(ShadowEvaluation).values(**values).on_conflict_do_nothing(
                index_elements=[ShadowEvaluation.fingerprint]).returning(ShadowEvaluation.id))
            row = session.get(ShadowEvaluation, row_id) if row_id else session.scalar(select(ShadowEvaluation).where(ShadowEvaluation.fingerprint == fingerprint))
            session.commit()
            return self.serialize(row)

    @staticmethod
    def serialize(row):
        return ShadowResult(**{key: getattr(row, key) for key in ("id", "case_id", "actor", "mode", "action_authorization", "execution_permitted", "outcome", "result", "created_at")})

    def list(self, case_id, access, limit=50, offset=0):
        require_access(access, case_id)
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid_shadow_page")
        with self.database.get_session() as session:
            if session.get(Case, case_id) is None:
                raise LookupError("case_not_found")
            return [self.serialize(row) for row in session.scalars(select(ShadowEvaluation).where(ShadowEvaluation.case_id == case_id)
                .order_by(ShadowEvaluation.created_at.desc(), ShadowEvaluation.id).limit(limit).offset(offset))]

    def comparison(self, case_id, access):
        require_access(access, case_id)
        with self.database.get_session() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            case = session.get(Case, case_id)
            if case is None:
                raise LookupError("case_not_found")
            verification = session.scalar(select(VerificationResult).where(VerificationResult.case_id == case_id)
                .order_by(VerificationResult.created_at.desc(), VerificationResult.id).limit(1))
            action = session.get(ActionRecord, verification.action_id) if verification and verification.action_id else None
            operation = session.scalar(select(ExecutionOperation).where(ExecutionOperation.case_id == case_id,
                ExecutionOperation.action_id == action.id)) if action else None
            verified = bool(verification and verification.success and verification.verification_type == "INDEPENDENT_SYNTHETIC_CONFIRMATION"
                and action and action.status == "VERIFIED" and operation and operation.status == "VERIFIED" and case.status.value == "RESOLVED")
            observations = session.scalars(select(ShadowEvaluation).where(ShadowEvaluation.case_id == case_id)
                .order_by(ShadowEvaluation.created_at.desc(), ShadowEvaluation.id).limit(101)).all()
            return {"case_id": case_id, "current_case_status": case.status.value, "independently_verified_resolution": verified,
                "verification_id": verification.id if verification else None,
                "verification_at": verification.created_at if verification else None,
                "shadow_results": [{"id": row.id, "hypothetical_outcome": row.outcome, "observed_at": row.created_at,
                    "verification_observed_after_shadow": bool(verification and verification.created_at >= row.created_at)} for row in observations[:100]],
                "truncated": len(observations) > 100,
                "limitation": "Current case outcome compared with hypothetical observations; this does not establish that a shadow proposal caused the outcome.",
                "execution_permitted": False}
