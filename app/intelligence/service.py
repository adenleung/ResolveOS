"""Bounded observed-data cohorts. No simulator tables, model calls or writes."""
from collections import defaultdict, Counter
from datetime import timedelta
from statistics import median
from sqlalchemy import select, func, or_

from app.classification.models import AssessmentHistory
from app.correlation.models import IncidentCorrelationHistory
from app.domain.case_service import CaseState
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import Case, ExceptionRecord, AuditLog, CaseIncident, Incident, VerificationResult
from app.investigation.models import InvestigationRun
from app.orchestration.models import WorkTask, TaskConsumer, TaskHistory
from app.controls.models import ActionApproval, ControlAuthorization, ActionApprovalHistory
from app.execution.models import ExecutionOperation
from app.intelligence.contracts import IntelligenceReport, IncidentRelationships, Reference, Finding, DurationMetric, Hypothesis
from app.orchestration.queue import utc

MAX_CASES = 500
MAX_ROWS = 2000
MAX_REFS = 20


def interval(start, end, cutoff):
    if start is None or end is None or utc(end) > cutoff:
        return None, "incomplete"
    seconds = (utc(end) - utc(start)).total_seconds()
    return (None, "invalid_order") if seconds < 0 else (seconds, "completed")


def ref(kind, row_id, case_id=None):
    return Reference(kind=kind, id=row_id, case_id=case_id)


def require_access(access, case_id=None):
    if not access.identity.user_id or not access.identity.roles.intersection({"WORKER", "OPERATIONS_REVIEWER"}):
        raise PermissionError("analytics_read_permission_required")
    if case_id is not None and access.case_ids is not None and case_id not in access.case_ids:
        raise PermissionError("analytics_case_not_granted")


class IntelligenceService:
    def __init__(self, session, access):
        require_access(access)
        self.session, self.access = session, access
        self.truncated = False

    def rows(self, statement, cap=MAX_ROWS):
        result = self.session.scalars(statement.limit(cap + 1)).all()
        self.truncated |= len(result) > cap
        return result[:cap]

    def report(self, start=None, end=None, case_limit=MAX_CASES):
        self.truncated = False
        now = utc(self.session.scalar(select(func.clock_timestamp())))
        end = self.aware(end) if end else now
        start = self.aware(start) if start else end - timedelta(days=30)
        if start >= end or end > now or end - start > timedelta(days=365) or not 1 <= case_limit <= MAX_CASES:
            raise ValueError("invalid_analytics_window_or_limit")
        cohort = select(Case).where(Case.created_at >= start, Case.created_at <= end)
        if self.access.case_ids is not None:
            cohort = cohort.where(Case.id.in_(self.access.case_ids))
        cases = self.rows(cohort.order_by(Case.created_at, Case.id), case_limit)
        ids = [case.id for case in cases]
        exceptions = self.rows(select(ExceptionRecord).where(ExceptionRecord.case_id.in_(ids),
            ExceptionRecord.created_at <= end).order_by(ExceptionRecord.id))
        exception_by_id = {row.id: row for row in exceptions}
        assessments = self.rows(select(AssessmentHistory).where(AssessmentHistory.case_id.in_(ids),
            AssessmentHistory.created_at <= end).order_by(AssessmentHistory.created_at.desc(), AssessmentHistory.id))
        latest = {}
        for assessment in assessments:
            latest.setdefault(assessment.exception_id, assessment)
        categories = defaultdict(list)
        for exception in exceptions:
            assessment = latest.get(exception.id)
            names = {item["category"] for item in assessment.assessment.get("classification", {}).get("categories", [])} if assessment else {"UNCLASSIFIED"}
            names = names or {"UNCLASSIFIED"}
            for name in names:
                categories[name].append((exception.case_id, ref("assessment" if assessment else "exception", assessment.id if assessment else exception.id, exception.case_id)))
        links = self.session.execute(select(ExceptionEvidence, EventRecord).join(EventRecord,
            EventRecord.id == ExceptionEvidence.event_record_id).where(ExceptionEvidence.exception_id.in_(exception_by_id),
            ExceptionEvidence.linked_at <= end, EventRecord.occurred_at <= end, EventRecord.ingested_at <= end)
            .order_by(ExceptionEvidence.id).limit(MAX_ROWS + 1)).all()
        self.truncated |= len(links) > MAX_ROWS
        systems, successes = defaultdict(dict), defaultdict(list)
        for link, event in links[:MAX_ROWS]:
            case_id = exception_by_id[link.exception_id].case_id
            source = event.source_system
            endpoint = event.payload.get("endpoint") if source == "api_gateway" else None
            key = source + (":" + str(endpoint)[:200] if endpoint else "")
            status = event.payload.get("status_code")
            if source == "api_gateway" and type(status) is int and status < 400:
                successes[key].append(ref("event", event.id, case_id))
            if source == "api_gateway":
                latency = event.payload.get("latency_ms")
                failed = (type(status) is int and status >= 500) or (type(latency) is int and latency >= 30000) or bool(event.payload.get("error_type"))
                if not failed:
                    continue
            # Each exception contributes once to a system/endpoint, even when
            # linked to multiple historical snapshots of the same source.
            systems[key][link.exception_id] = (case_id, ref("event", event.id, case_id))
        consumers = select(TaskConsumer.task_id).where(TaskConsumer.case_id.in_(ids))
        tasks = self.rows(select(WorkTask).where(or_(WorkTask.case_id.in_(ids), WorkTask.id.in_(consumers)),
            WorkTask.created_at <= end).order_by(WorkTask.created_at, WorkTask.id))
        task_ids = [task.id for task in tasks]
        runs = self.rows(select(InvestigationRun).where(InvestigationRun.task_id.in_(task_ids),
            InvestigationRun.started_at <= end).order_by(InvestigationRun.started_at, InvestigationRun.id))
        histories = self.rows(select(TaskHistory).where(TaskHistory.task_id.in_(task_ids),
            TaskHistory.created_at <= end).order_by(TaskHistory.created_at, TaskHistory.id))
        audits = self.rows(select(AuditLog).where(AuditLog.case_id.in_(ids), AuditLog.created_at <= end)
            .order_by(AuditLog.created_at, AuditLog.id))
        verifications = self.rows(select(VerificationResult).where(VerificationResult.case_id.in_(ids),
            VerificationResult.created_at <= end, VerificationResult.verification_type == "INDEPENDENT_SYNTHETIC_CONFIRMATION")
            .order_by(VerificationResult.created_at, VerificationResult.id))
        operations = self.rows(select(ExecutionOperation).where(ExecutionOperation.case_id.in_(ids),
            ExecutionOperation.created_at <= end).order_by(ExecutionOperation.created_at, ExecutionOperation.id))
        approvals = self.session.execute(select(ActionApproval, ControlAuthorization).join(ControlAuthorization,
            ControlAuthorization.id == ActionApproval.authorization_id).where(ControlAuthorization.case_id.in_(ids),
            ActionApproval.created_at <= end).order_by(ActionApproval.created_at, ActionApproval.id).limit(MAX_ROWS + 1)).all()
        self.truncated |= len(approvals) > MAX_ROWS
        approvals = approvals[:MAX_ROWS]
        approval_history = self.rows(select(ActionApprovalHistory).where(ActionApprovalHistory.approval_id.in_([a.id for a, _ in approvals]),
            ActionApprovalHistory.created_at <= end).order_by(ActionApprovalHistory.created_at, ActionApprovalHistory.id))

        groups = defaultdict(list)
        for audit in audits:
            if audit.event_type == "orchestration_case_transition" and audit.details.get("current") == "ESCALATED":
                groups["escalation"].append((audit.case_id, ref("audit", audit.id, audit.case_id)))
            if audit.event_type in {"orchestration_routing_changed", "case_work_superseded", "incident_coordination_changed"}:
                groups["handover"].append((audit.case_id, ref("audit", audit.id, audit.case_id)))
        seen_investigations = Counter()
        for run in runs:
            if run.case_id in ids:
                groups["investigation_attempt"].append((run.case_id, ref("investigation", run.id, run.case_id)))
                if seen_investigations[(run.case_id, run.role)]:
                    groups["reinvestigation"].append((run.case_id, ref("investigation", run.id, run.case_id)))
                seen_investigations[(run.case_id, run.role)] += 1
                if (run.result or {}).get("missing_evidence"):
                    groups["reported_missing_evidence"].append((run.case_id, ref("investigation", run.id, run.case_id)))
        for verification in verifications:
            if not verification.success:
                groups["independent_verification_failure"].append((verification.case_id, ref("verification", verification.id, verification.case_id)))
        for assessment in latest.values():
            if "missing_evidence" in assessment.assessment.get("classification", {}).get("uncertainty_flags", []):
                groups["classification_missing_evidence"].append((assessment.case_id, ref("assessment", assessment.id, assessment.case_id)))

        observations = defaultdict(list)
        def measure(key, start_time, end_time, reference):
            seconds, status = interval(start_time, end_time, end)
            observations[key].append((seconds, status, reference))
        first_assessment = {}
        for assessment in sorted(assessments, key=lambda row: (row.created_at, row.id)):
            first_assessment.setdefault(assessment.exception_id, assessment)
        for exception in exceptions:
            first = first_assessment.get(exception.id)
            measure("detection_to_classification", exception.detected_at, first.created_at if first else None, ref("exception", exception.id, exception.case_id))
        first_claim = {}
        for history in histories:
            if history.event_type == "task_claimed":
                first_claim.setdefault(history.task_id, history.created_at)
        for task in tasks:
            if task.task_type.startswith("INVESTIGATE_"):
                measure("investigation_queue_wait", task.created_at, first_claim.get(task.id), ref("task", task.id, task.case_id if task.case_id in ids else None))
        for run in runs:
            measure("investigation_attempt_duration", run.started_at, run.completed_at, ref("investigation", run.id, run.case_id if run.case_id in ids else None))
        for approval, authorization in approvals:
            decision = next((h for h in approval_history if h.approval_id == approval.id and h.operation in {"APPROVE", "REJECT", "MORE_INVESTIGATION"}), None)
            measure("human_action_approval_wait", approval.created_at, decision.created_at if decision else None, ref("approval", approval.id, authorization.case_id))
        for operation in operations:
            # completed_at is the end of independent verification, not the
            # confirmation-effect timestamp. Never label it execution-only latency.
            measure("execution_to_verification", operation.created_at, operation.completed_at, ref("operation", operation.id, operation.case_id))
            effect = next((a for a in audits if a.event_type == "synthetic_confirmation_replayed" and a.details.get("action_id") == operation.action_id), None)
            measure("execution_queue_to_effect", operation.created_at, effect.created_at if effect else None, ref("operation", operation.id, operation.case_id))
            verification = next((v for v in verifications if v.action_id == operation.action_id), None)
            measure("effect_to_independent_verification", effect.created_at if effect else None, verification.created_at if verification else None, ref("operation", operation.id, operation.case_id))
        latest_verification = {v.case_id: v for v in verifications}
        verified_cases = set()
        for case in cases:
            verification = latest_verification.get(case.id)
            verified = bool(verification and verification.success and case.status == CaseState.RESOLVED and
                any(op.action_id == verification.action_id and op.status == "VERIFIED" for op in operations))
            if verified:
                verified_cases.add(case.id)
            measure("total_independently_verified_resolution", case.created_at, verification.created_at if verified else None, ref("case", case.id, case.id))
        bottlenecks = []
        for key in ("detection_to_classification", "investigation_queue_wait", "investigation_attempt_duration",
                    "human_action_approval_wait", "execution_to_verification", "execution_queue_to_effect",
                    "effect_to_independent_verification", "total_independently_verified_resolution"):
            values = observations[key]
            completed = [v for v, status, _ in values if status == "completed"]
            bottlenecks.append(DurationMetric(key=key, completed=len(completed), incomplete=sum(s == "incomplete" for _, s, _ in values),
                invalid_order=sum(s == "invalid_order" for _, s, _ in values), median_seconds=median(completed) if completed else None,
                maximum_seconds=max(completed) if completed else None, references=[r for _, _, r in values][:MAX_REFS],
                method="Per observation interval; completed pairs only. Parallel attempts are not added together; missing/future ends are incomplete."))
        system_findings = [self.finding(key, list(value.values()), "Distinct linked exception IDs per observed system/endpoint; not independent incident counts.") for key, value in sorted(systems.items())]
        hypotheses = []
        for finding in system_findings:
            if finding.count >= 2:
                hypotheses.append(Hypothesis(suspected_factor="Recurring exception observations involving " + finding.key,
                    supporting_evidence=finding.references, contradictory_evidence=successes[finding.key][:MAX_REFS],
                    affected_cases=finding.case_ids, missing_information=["Independent causal attribution", "Complete service denominator and health history"],
                    next_step="Inspect linked current observations and compare affected/unaffected requests; validate dependency history.",
                    confidence_limitation="Repeated association is not proven common causation. Successful requests may coexist; cohort and reference caps apply."))
        prevention = list(hypotheses)
        for key, values in sorted(groups.items()):
            if len(values) >= 2 and key in {"reported_missing_evidence", "classification_missing_evidence", "independent_verification_failure"}:
                prevention.append(Hypothesis(suspected_factor="Review recurring " + key.replace("_", " "),
                    supporting_evidence=[r for _, r in values][:MAX_REFS], contradictory_evidence=[], affected_cases=sorted({c for c, _ in values}),
                    missing_information=["Root cause of each observation", "Unobserved or truncated records"],
                    next_step="Review the linked cases and propose a human-approved evidence or verification improvement.",
                    confidence_limitation="Advisory candidate only; cannot modify policies, routing, permissions or banking records."))
        return IntelligenceReport(version="operational-intelligence-1.0", generated_at=now, window_start=start, window_end=end,
            case_count=len(cases), truncated=self.truncated, limits={"cases": case_limit, "rows_per_kind": MAX_ROWS, "references_per_finding": MAX_REFS},
            overview={"open_cases": sum(c.status not in {CaseState.RESOLVED, CaseState.BLOCKED, CaseState.ESCALATED, CaseState.FAILED} for c in cases),
                "awaiting_human": sum(c.status == CaseState.AWAITING_HUMAN for c in cases), "verified_resolutions": len(verified_cases),
                "sla_overdue_current": sum(bool(c.sla_deadline and utc(c.sla_deadline) < now and c.status not in {CaseState.RESOLVED, CaseState.BLOCKED, CaseState.ESCALATED, CaseState.FAILED}) for c in cases),
                "exceptions": len(exceptions), **{"priority_" + p.lower(): sum(c.priority == p for c in cases) for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}},
            categories=[self.finding(key, value, "Latest recorded classification per exception at window end; categories may overlap; unclassified is explicit.") for key, value in sorted(categories.items())],
            systems=system_findings, recurrences=[self.finding(key, value, "Count persisted observations, not independent incident families or inferred causes.") for key, value in sorted(groups.items())],
            bottlenecks=bottlenecks, hypotheses=hypotheses, prevention=prevention,
            limitations=["Cohort selects cases created in the window; older active cases are outside this report.",
                "Overview status/priority/SLA fields are current projections, not historical reconstruction.",
                "Rows and reference lists are bounded. Truncated results are partial and must not be used as population-wide rates.",
                "Investigator missing-evidence statements are reported claims, not independent proof.",
                "No historical SLA-breach rate is inferred from mutable current deadlines."])

    @staticmethod
    def aware(value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return utc(value)

    @staticmethod
    def finding(key, values, method):
        return Finding(key=key, count=len(values), case_ids=sorted({c for c, _ in values}), references=[r for _, r in values][:MAX_REFS],
            method=method, limitation="Bounded cohort; up to 20 evidence references displayed. Counts are observations, not proof of independent common causes.")

    def relationships(self, incident_id):
        self.truncated = False
        if self.session.get(Incident, incident_id) is None:
            raise LookupError("incident_not_found")
        if self.access.case_ids is not None and self.session.scalar(select(CaseIncident.id).where(
                CaseIncident.incident_id == incident_id, CaseIncident.case_id.not_in(self.access.case_ids)).limit(1)):
            raise PermissionError("incident_case_scope_incomplete")
        members = self.rows(select(CaseIncident).where(CaseIncident.incident_id == incident_id).order_by(CaseIncident.created_at, CaseIncident.id), 500)
        if self.access.case_ids is not None:
            if not members or any(m.case_id not in self.access.case_ids for m in members):
                raise PermissionError("incident_case_scope_incomplete")
        history = self.rows(select(IncidentCorrelationHistory).where(IncidentCorrelationHistory.incident_id == incident_id)
            .order_by(IncidentCorrelationHistory.created_at, IncidentCorrelationHistory.id), 100)
        if self.access.case_ids is not None and any(not set(h.case_ids).issubset(self.access.case_ids) for h in history):
            raise PermissionError("incident_history_scope_incomplete")
        return IncidentRelationships(incident_id=incident_id, case_ids=sorted({m.case_id for m in members if m.removed_at is None}),
            memberships=[{"id": m.id, "case_id": m.case_id, "created_at": m.created_at.isoformat(), "removed_at": m.removed_at.isoformat() if m.removed_at else None,
                          "removal_reason": m.removal_reason, "history_id": m.correlation_history_id} for m in members],
            history=[{"id": h.id, "operation": h.operation, "outcome": h.outcome, "created_at": h.created_at.isoformat(), "case_ids": h.case_ids,
                      "evidence_references": h.evidence_references} for h in history],
            shared_observations=[{"history_id": h.id, "observations": h.shared_features} for h in history],
            contradictions=[{"history_id": h.id, "observations": h.contradictions} for h in history if h.contradictions],
            truncated=self.truncated, limitation="Suspected relationships use persisted observed correlation history; similarity does not prove causation. Removed memberships remain historical.")
