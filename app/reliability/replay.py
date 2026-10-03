"""Recorded decision timeline; mutable present-day fields never masquerade as history."""
from sqlalchemy import select, func, or_
from app.intelligence.service import require_access
from app.reliability.contracts import ReplayReport
from app.orchestration.queue import utc
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import Case, ExceptionRecord, Evidence, VerificationResult, AuditLog, CaseIncident
from app.classification.models import AssessmentHistory
from app.investigation.models import InvestigationRun
from app.supervisor.models import SupervisorReview
from app.controls.models import ControlAuthorization, ActionApprovalHistory, ActionApproval
from app.execution.models import ExecutionOperation, CounterfactualSimulation
from app.orchestration.models import TaskConsumer, WorkTask, ReviewHistory, WorkflowReview
from app.investigation.tools import clean_payload


class ReplayService:
    def __init__(self, session, access):
        require_access(access)
        self.session, self.access = session, access
        self.truncated = False

    def rows(self, query, cap=500):
        rows = self.session.scalars(query.limit(cap + 1)).all()
        self.truncated |= len(rows) > cap
        return rows[:cap]

    def replay(self, case_id, as_of=None):
        require_access(self.access, case_id)
        self.truncated = False
        now = utc(self.session.scalar(select(func.clock_timestamp())))
        if as_of and as_of.tzinfo is None:
            raise ValueError("timezone_required")
        cutoff = utc(as_of) if as_of else now
        case = self.session.get(Case, case_id)
        if case is None:
            raise LookupError("case_not_found")
        if cutoff > now or utc(case.created_at) > cutoff:
            raise ValueError("invalid_replay_time")
        event_links = self.session.execute(select(EventRecord, ExceptionEvidence).join(ExceptionEvidence,
            ExceptionEvidence.event_record_id == EventRecord.id).join(ExceptionRecord, ExceptionRecord.id == ExceptionEvidence.exception_id)
            .where(ExceptionRecord.case_id == case_id).order_by(EventRecord.occurred_at, EventRecord.id).limit(501)).all()
        self.truncated |= len(event_links) > 500
        known, later = {}, {}
        for event, link in event_links[:500]:
            known_at = max(utc(event.occurred_at), utc(event.ingested_at), utc(link.linked_at))
            entry = {"id": event.id, "source_system": event.source_system, "occurred_at": event.occurred_at.isoformat(),
                     "ingested_at": event.ingested_at.isoformat(), "linked_at": link.linked_at.isoformat(),
                     "known_at": known_at.isoformat(), "payload": clean_payload(event.payload)}
            (known if known_at <= cutoff else later)[event.id] = entry
        for event_id in known:
            later.pop(event_id, None)
        # Investigation evidence may be retrieved separately from detector links.
        for evidence in self.rows(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.retrieval_timestamp, Evidence.id)):
            event_id = (evidence.integrity_metadata or {}).get("event_record_id")
            event = self.session.get(EventRecord, event_id) if event_id else None
            if event is None or evidence.payload != clean_payload(event.payload) or evidence.source_system != event.source_system or evidence.source_record_id != event.source_record_reference:
                continue  # Unknown provenance is never promoted to known evidence.
            known_at = max(utc(event.occurred_at), utc(event.ingested_at), utc(evidence.retrieval_timestamp))
            entry = {"id": event.id, "source_system": event.source_system, "occurred_at": event.occurred_at.isoformat(),
                     "ingested_at": event.ingested_at.isoformat(), "retrieved_at": evidence.retrieval_timestamp.isoformat(),
                     "known_at": known_at.isoformat(), "payload": clean_payload(event.payload)}
            # Keep the earliest genuinely available route to each observation.
            if event.id not in known:
                (known if known_at <= cutoff else later)[event.id] = entry
            if event.id in known:
                later.pop(event.id, None)
        timeline = []
        def add(kind, row_id, timestamp, payload, actor=None, basis="RECORDED_HISTORY"):
            if timestamp and utc(timestamp) <= cutoff:
                timeline.append({"kind": kind, "id": row_id, "at": utc(timestamp).isoformat(), "actor": actor,
                                 "basis": basis, "payload": payload})
        for exception in self.rows(select(ExceptionRecord).where(ExceptionRecord.case_id == case_id).order_by(ExceptionRecord.id)):
            add("DETECTED", exception.id, exception.detected_at, {"exception_type": exception.exception_type})
        for assessment in self.rows(select(AssessmentHistory).where(AssessmentHistory.case_id == case_id,
                AssessmentHistory.created_at <= cutoff).order_by(AssessmentHistory.created_at, AssessmentHistory.id)):
            # Do not re-export raw historical feature payloads that could include
            # source observations whose historical availability cannot be proved.
            add("CLASSIFIED", assessment.id, assessment.created_at, {
                "categories": [c["category"] for c in assessment.assessment.get("classification", {}).get("categories", [])],
                "classification_source": assessment.classification_source, "assessment_version": assessment.assessment_version,
                "priority": assessment.assessment.get("priority", {}).get("level")}, basis="RECORDED_ASSESSMENT")
        related = select(TaskConsumer.task_id).where(TaskConsumer.case_id == case_id)
        for run in self.rows(select(InvestigationRun).where(or_(InvestigationRun.case_id == case_id, InvestigationRun.task_id.in_(related)))
                .order_by(InvestigationRun.started_at, InvestigationRun.id)):
            add("INVESTIGATION_STARTED", run.id, run.started_at, {"role": run.role, "attempt": run.attempt}, run.model)
            add("INVESTIGATION_COMPLETED", run.id, run.completed_at, {"role": run.role, "status": run.status,
                "summary": (run.result or {}).get("summary"), "missing_evidence": (run.result or {}).get("missing_evidence", [])}, run.model, "RECORDED_INTERPRETATION")
        for review in self.rows(select(SupervisorReview).where(SupervisorReview.case_id == case_id,
                SupervisorReview.created_at <= cutoff).order_by(SupervisorReview.created_at, SupervisorReview.id)):
            add("SUPERVISOR_REVIEW", review.id, review.created_at, {"outcome": review.outcome,
                "summary": review.result.get("summary"), "proposed_action": review.result.get("proposed_action"),
                "unresolved_issues": review.result.get("unresolved_issues", [])}, review.model, "RECORDED_INTERPRETATION")
        authorizations = self.rows(select(ControlAuthorization).where(ControlAuthorization.case_id == case_id,
            ControlAuthorization.created_at <= cutoff).order_by(ControlAuthorization.created_at, ControlAuthorization.id))
        for authorization in authorizations:
            add("DETERMINISTIC_CONTROL", authorization.id, authorization.created_at, {"outcome": authorization.outcome,
                "action": authorization.action, "reasons": authorization.reasons, "policy_version_id": authorization.policy_version_id,
                "recorded_policy_hash": authorization.snapshot.get("policy_hash")})
        approval_ids = select(ActionApproval.id).where(ActionApproval.authorization_id.in_([a.id for a in authorizations]))
        for history in self.rows(select(ActionApprovalHistory).where(ActionApprovalHistory.approval_id.in_(approval_ids),
                ActionApprovalHistory.created_at <= cutoff).order_by(ActionApprovalHistory.created_at, ActionApprovalHistory.id)):
            add("ACTION_APPROVAL_" + history.operation, history.id, history.created_at, {"approval_id": history.approval_id, "reason": history.reason}, history.actor)
        review_ids = select(WorkflowReview.id).where(WorkflowReview.case_id == case_id)
        for history in self.rows(select(ReviewHistory).where(ReviewHistory.review_id.in_(review_ids), ReviewHistory.created_at <= cutoff)
                .order_by(ReviewHistory.created_at, ReviewHistory.id)):
            add("WORKFLOW_REVIEW_" + history.operation, history.id, history.created_at, {"review_id": history.review_id, "reason": history.reason}, history.actor)
        for simulation in self.rows(select(CounterfactualSimulation).where(CounterfactualSimulation.case_id == case_id,
                CounterfactualSimulation.created_at <= cutoff).order_by(CounterfactualSimulation.created_at, CounterfactualSimulation.id)):
            add("SIMULATED", simulation.id, simulation.created_at, {"outcome": simulation.outcome, "projection": simulation.projection}, basis="HYPOTHETICAL")
        for audit in self.rows(select(AuditLog).where(AuditLog.case_id == case_id, AuditLog.created_at <= cutoff)
                .order_by(AuditLog.created_at, AuditLog.id)):
            add(audit.event_type, audit.id, audit.created_at, {"summary": audit.summary,
                "previous": audit.details.get("previous"), "current": audit.details.get("current"),
                "action_id": audit.details.get("action_id")}, audit.details.get("actor"))
        for verification in self.rows(select(VerificationResult).where(VerificationResult.case_id == case_id,
                VerificationResult.created_at <= cutoff).order_by(VerificationResult.created_at, VerificationResult.id)):
            add("INDEPENDENT_VERIFICATION" if verification.verification_type == "INDEPENDENT_SYNTHETIC_CONFIRMATION" else "UNSUPPORTED_VERIFICATION_RECORD",
                verification.id, verification.created_at, {"success": verification.success, "action_id": verification.action_id,
                    "verification_type": verification.verification_type, "detail": verification.detail})
        for membership in self.rows(select(CaseIncident).where(CaseIncident.case_id == case_id).order_by(CaseIncident.created_at, CaseIncident.id)):
            add("INCIDENT_MEMBERSHIP_ADDED", membership.id, membership.created_at, {"incident_id": membership.incident_id})
            add("INCIDENT_MEMBERSHIP_REMOVED", membership.id, membership.removed_at, {"incident_id": membership.incident_id, "reason": membership.removal_reason})
        timeline.sort(key=lambda row: (row["at"], row["kind"], row["id"]))
        return ReplayReport(case_id=case_id, as_of=cutoff, evidence_known_at_time=sorted(known.values(), key=lambda e: (e["known_at"], e["id"])),
            evidence_observed_later=sorted(later.values(), key=lambda e: (e["known_at"], e["id"])), timeline=timeline, truncated=self.truncated,
            reconstruction_limitations=["Recorded timeline, not a rerun of historical decisions; mutable current statuses and policy contents are not exported as past facts.",
                "Original policy hash/version is retained; policy content edited in place cannot be fully reconstructed.",
                "Only normalized occurrence+ingestion+link/retrieval times prove evidence availability. Unknown provenance is omitted.",
                "Historical model text is recorded interpretation, never independently established fact.",
                "Each record kind is capped at 500; truncation is explicit. No replay executes or authorizes an action."])
