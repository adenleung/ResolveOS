from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, func, select, text

from app.classification.models import AssessmentHistory
from app.classification.service import ClassificationService
from app.correlation.models import IncidentCorrelationHistory
from app.correlation.service import CORRELATION_ADVISORY_LOCK
from app.domain.case_service import CaseState
from app.ingestion.models import EventRecord
from app.models.domain import AuditLog, Case, CaseIncident, ExceptionRecord, Incident
from app.orchestration.contracts import ACTIVE_TASKS, INVESTIGATION_TASKS, TaskPayload, TaskType, WORKFLOW_VERSION
from app.orchestration.models import ReviewHistory, TaskConsumer, TaskHistory, WorkflowReview, WorkTask
from app.orchestration.queue import LeaseLost, WorkQueue, digest, utc

PRIORITIES = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
TERMINAL_CASES = {CaseState.RESOLVED, CaseState.FAILED, CaseState.BLOCKED, CaseState.ESCALATED}
ROUTABLE_CASES = {CaseState.DETECTED, CaseState.TRIAGED, CaseState.INVESTIGATION_QUEUED,
                  CaseState.INVESTIGATING, CaseState.AWAITING_DECISION, CaseState.AWAITING_HUMAN}


class OrchestrationService:
    def __init__(self, session, settings=None, clock=None):
        self.session = session
        self.queue = WorkQueue(session, settings, clock)
        self.settings = self.queue.settings

    def case(self, case_id, lock=False):
        # Runtime sessions disable autoflush; persist local changes before refreshing.
        self.session.flush()
        query = select(Case).where(Case.id == case_id).execution_options(populate_existing=True)
        if lock:
            query = query.with_for_update()
        result = self.session.execute(query).scalar_one_or_none()
        if result is None:
            raise LookupError("case_not_found")
        return result

    def audit(self, case, operation, details):
        self.session.add(AuditLog(id=str(uuid4()), case_id=case.id, entity_type="case",
            entity_id=case.id, event_type=operation, summary=operation.replace("_", " "),
            details={"workflow_version": WORKFLOW_VERSION, "action_authorization": "NOT_EVALUATED", **details}))

    def transition(self, case, target, reason):
        if case.status == target:
            return
        previous = case.status.value
        case.transition_to(target)
        self.audit(case, "orchestration_case_transition", {"previous": previous, "current": target.value, "reason": reason})

    def assessments(self, case_ids):
        # Correlated indexed revision lookup, restricted to the relevant cases.
        latest = select(AssessmentHistory.exception_id, func.max(AssessmentHistory.revision).label("revision")).where(
            AssessmentHistory.case_id.in_(case_ids)).group_by(AssessmentHistory.exception_id).subquery()
        return self.session.execute(select(AssessmentHistory).join(latest, and_(
            AssessmentHistory.exception_id == latest.c.exception_id, AssessmentHistory.revision == latest.c.revision
        )).order_by(AssessmentHistory.id).limit(501)).scalars().all()

    def evidence_stamp(self, case):
        entities = self.session.execute(select(ExceptionRecord.source_reference).where(ExceptionRecord.case_id == case.id)).scalars().all()
        # No payload/ground-truth reads: aggregate observed event revisions only.
        count, latest = self.session.execute(select(func.count(EventRecord.id), func.max(EventRecord.ingested_at)).where(
            EventRecord.entity_reference.in_([entity for entity in entities if entity]))).one()
        membership = self.session.execute(select(CaseIncident.id, Incident.id, Incident.status, Incident.updated_at)
            .join(Incident, Incident.id == CaseIncident.incident_id).where(CaseIncident.case_id == case.id,
                CaseIncident.removed_at.is_(None))).all()
        incident_stamp = None
        if membership:
            member_ids = select(CaseIncident.case_id).where(CaseIncident.incident_id == membership[0][1],
                CaseIncident.removed_at.is_(None))
            incident_stamp = self.session.execute(select(func.count(AssessmentHistory.id), func.max(AssessmentHistory.created_at))
                .where(AssessmentHistory.case_id.in_(member_ids))).one()
        return digest([count, latest, case.orchestration_generation, [item.id for item in self.assessments([case.id])],
                       [tuple(row) for row in membership], tuple(incident_stamp) if incident_stamp else None])

    def payload(self, case, task_type, assessments=None, incident_id=None, context=None, reason="Operational case work"):
        assessments = assessments or []
        refs = {}
        versions = {}
        for assessment in assessments:
            classification = assessment.assessment.get("classification", {})
            versions[assessment.id] = classification.get("rule_version", assessment.assessment_version)
            for category in classification.get("categories", []):
                for reference in category.get("supporting_evidence_references", []):
                    # Emit approved reference metadata only, never arbitrary source payload/labels.
                    clean = {key: reference[key] for key in ("event_record_id", "event_id", "source_system", "entity_reference", "source_record_reference") if key in reference}
                    refs[clean.get("event_record_id", digest(clean))] = clean
        future = task_type.value not in {"CLASSIFY_CASE", "ROUTE_CASE", "REEVALUATE_CASE", "CHECK_SLA"}
        return TaskPayload(case_id=case.id, task_type=task_type, incident_id=incident_id,
            assessment_ids=[assessment.id for assessment in assessments], assessment_versions=versions,
            evidence_references=list(refs.values())[:2000],
            evidence_truncated=len(refs) > 2000,
            permitted_tool_scope=["READ_CASE_EVIDENCE"] + (["READ_INCIDENT_CONTEXT"] if incident_id else []) if future else [],
            deadline=utc(case.sla_deadline) if future and case.sla_deadline else (self.queue.now() + timedelta(hours=24) if future else None),
            incident_context=context, reason=reason)

    def schedule_case(self, case_id, *, reevaluate=False, commit=True):
        self.queue.require_postgres()
        case = self.case(case_id, lock=True)
        if case.status in TERMINAL_CASES or case.status not in ROUTABLE_CASES:
            return self.finish({"case_id": case_id, "scheduled": [], "reason": "case_not_eligible"}, commit)
        kind = TaskType.REEVALUATE_CASE if reevaluate else TaskType.CLASSIFY_CASE
        stamp = self.evidence_stamp(case)
        task = self.queue.schedule(self.payload(case, kind), f"{kind.value}:{case.id}:{stamp}", PRIORITIES.get(case.priority, 2))
        self.queue.consumer(task, case.id, [])
        self._schedule_sla(case)
        return self.finish({"case_id": case.id, "scheduled": [task.id]}, commit)

    def finish(self, result, commit=True):
        self.session.commit() if commit else self.session.flush()
        return result

    def _schedule_sla(self, case):
        if case.sla_deadline is None or case.status in TERMINAL_CASES:
            return None
        now = self.queue.now()
        due = max(now, min(utc(case.sla_deadline), now + timedelta(seconds=self.settings.orchestration_sla_interval_seconds)))
        slot = int(due.timestamp()) // self.settings.orchestration_sla_interval_seconds
        task = self.queue.schedule(self.payload(case, TaskType.CHECK_SLA),
            f"sla:{case.id}:{case.sla_deadline.isoformat()}:{slot}", PRIORITIES.get(case.priority, 2), due)
        self.queue.consumer(task, case.id, [])
        return task

    def _incident_context(self, case):
        # Matches Phase 5's transaction lock, so membership cannot change mid-routing.
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CORRELATION_ADVISORY_LOCK})
        incident = self.session.execute(select(Incident).join(CaseIncident, CaseIncident.incident_id == Incident.id).where(
            CaseIncident.case_id == case.id, CaseIncident.removed_at.is_(None),
            Incident.status.in_(["SUSPECTED", "INVESTIGATING", "CONFIRMED"]))).scalar_one_or_none()
        if incident is None:
            return None, None, []
        members = self.session.execute(select(CaseIncident.case_id).where(CaseIncident.incident_id == incident.id,
            CaseIncident.removed_at.is_(None)).order_by(CaseIncident.case_id).limit(501)).scalars().all()
        if len(members) > 500:
            self.audit(case, "incident_context_deferred", {"incident_id": incident.id, "reason": "membership_bound_exceeded"})
            return None, None, []
        assessments = self.assessments(members)
        if len(assessments) > 500:
            self.audit(case, "incident_context_deferred", {"incident_id": incident.id, "reason": "assessment_bound_exceeded"})
            return None, None, []
        revision = self.session.execute(select(IncidentCorrelationHistory.id).where(IncidentCorrelationHistory.incident_id == incident.id)
            .order_by(IncidentCorrelationHistory.created_at.desc(), IncidentCorrelationHistory.id.desc()).limit(1)).scalar_one_or_none()
        context = {"incident_id": incident.id, "status": incident.status, "case_ids": members,
                   "history_revision": revision, "shared_authorization": False}
        context["fingerprint"] = digest([context, [item.id for item in assessments]])
        return incident.id, context, assessments

    def route_case(self, case, *, force=False):
        assessments = self.assessments([case.id])
        incident_id, context, incident_assessments = self._incident_context(case)
        fingerprint = digest([[item.id for item in assessments], context])
        context_changed = fingerprint != case.orchestration_fingerprint or force
        if context_changed:
            case.orchestration_generation += 1
            case.orchestration_fingerprint = fingerprint
            self._detach_old_work(case, "Assessment or incident context changed")
            for review in self.session.execute(select(WorkflowReview).where(WorkflowReview.case_id == case.id,
                WorkflowReview.status == "OPEN").with_for_update()).scalars():
                review.status = "SUPERSEDED"
                self.review_history(review, "orchestrator", "SUPERSEDED", "Current context changed")
            self.audit(case, "orchestration_routing_changed", {"assessment_ids": [item.id for item in assessments],
                "incident_id": incident_id, "generation": case.orchestration_generation})
        if case.status not in ROUTABLE_CASES:
            return []
        if case.status == CaseState.DETECTED:
            self.transition(case, CaseState.TRIAGED, "Assessment processed")
        recommendations = set()
        triage = not assessments
        for assessment in assessments:
            routing = assessment.assessment.get("routing", {})
            recommendations.update(routing.get("recommended_specialists", []))
            triage |= routing.get("human_triage_required", True)
        if triage:
            self._request_review(case, assessments, "Ambiguous, incomplete or unsupported classification", context)
            return []
        tasks = []
        for specialist in sorted(recommendations):
            kind = TaskType(f"INVESTIGATE_{specialist}")
            if not context_changed:
                # A targeted Supervisor follow-up can replace one role while retaining
                # other valid results. Polling must not recreate every specialist.
                existing = self.session.execute(select(WorkTask, TaskConsumer).join(
                    TaskConsumer, TaskConsumer.task_id == WorkTask.id).where(
                    TaskConsumer.case_id == case.id, TaskConsumer.active.is_(True),
                    WorkTask.task_type == kind.value,
                    WorkTask.status.not_in(["CANCELLED", "DEAD_LETTER"]))
                    .order_by(WorkTask.created_at.desc()).limit(1)).first()
                if existing and sorted(existing[1].assessment_ids) == sorted(item.id for item in assessments):
                    tasks.append(existing[0].id)
                    continue
            shared = incident_id is not None and specialist == "TECHNOLOGY"
            task_assessments = incident_assessments if shared else assessments
            payload = self.payload(case, kind, task_assessments, incident_id, context)
            scope = f"incident:{incident_id}:{context['fingerprint']}" if shared else f"case:{case.id}:{case.orchestration_generation}"
            # Shared task has one immutable owner payload plus explicit per-case consumers.
            task = self.queue.schedule(payload, f"investigation:{scope}:{specialist}", PRIORITIES.get(case.priority, 2))
            if shared:
                # Invalidate obsolete shared work immediately; other cases attach to the
                # replacement on their next bounded poll without changing their status.
                obsolete = self.session.execute(select(WorkTask).where(WorkTask.incident_id == incident_id,
                    WorkTask.task_type == kind.value, WorkTask.id != task.id, WorkTask.status.in_(ACTIVE_TASKS))
                    .order_by(WorkTask.id).limit(500).with_for_update().execution_options(populate_existing=True)).scalars().all()
                for previous in obsolete:
                    consumers = self.session.execute(select(TaskConsumer).where(TaskConsumer.task_id == previous.id,
                        TaskConsumer.active.is_(True)).with_for_update().execution_options(populate_existing=True)).scalars().all()
                    for consumer in consumers:
                        consumer.active = False
                    self.queue.cancel(previous, "Shared incident assessment context superseded")
                    self.audit(case, "incident_coordination_changed", {"incident_id": incident_id,
                        "old_task_id": previous.id, "replacement_task_id": task.id,
                        "affected_case_ids": [consumer.case_id for consumer in consumers]})
            self.queue.consumer(task, case.id, [item.id for item in assessments])
            tasks.append(task.id)
            if shared:
                self.audit(case, "incident_investigation_coordinated", {"task_id": task.id, "incident_id": incident_id,
                    "assessment_ids": [item.id for item in assessments]})
        if case.status in {CaseState.TRIAGED, CaseState.AWAITING_HUMAN, CaseState.INVESTIGATING}:
            self.transition(case, CaseState.INVESTIGATION_QUEUED, "Relevant specialists scheduled; implementations unavailable")
        self._schedule_sla(case)
        return tasks

    def _detach_old_work(self, case, reason):
        links = self.session.execute(select(TaskConsumer, WorkTask).join(WorkTask, WorkTask.id == TaskConsumer.task_id).where(
            TaskConsumer.case_id == case.id, TaskConsumer.active.is_(True),
            WorkTask.task_type.in_(INVESTIGATION_TASKS | {"REQUEST_HUMAN_REVIEW", "REQUEST_SUPERVISOR_REVIEW"})
        ).with_for_update(of=[TaskConsumer, WorkTask]).execution_options(populate_existing=True)).all()
        for consumer, task in links:
            consumer.active = False
            self.session.flush()
            remaining = self.session.execute(select(TaskConsumer.id).where(TaskConsumer.task_id == task.id,
                TaskConsumer.active.is_(True)).limit(1)).scalar_one_or_none()
            if remaining is None:
                self.queue.cancel(task, reason)
            self.audit(case, "incident_coordination_changed" if task.incident_id else "case_work_superseded",
                {"task_id": task.id, "incident_id": task.incident_id, "reason": reason})

    def _request_review(self, case, assessments, reason, context=None, key_suffix=None):
        if case.status in {CaseState.DETECTED, CaseState.TRIAGED, CaseState.INVESTIGATION_QUEUED,
                           CaseState.INVESTIGATING, CaseState.AWAITING_DECISION}:
            if case.status == CaseState.DETECTED:
                self.transition(case, CaseState.TRIAGED, "Human triage required")
            self.transition(case, CaseState.AWAITING_HUMAN, reason)
        key = f"review:{case.id}:{case.orchestration_generation}:{key_suffix or digest(reason)}"
        existing = self.session.execute(select(WorkflowReview).where(WorkflowReview.idempotency_key == key)).scalar_one_or_none()
        if existing:
            return existing
        payload = self.payload(case, TaskType.REQUEST_HUMAN_REVIEW, assessments,
            context.get("incident_id") if context else None, context, reason)
        # A review after an SLA breach must still offer time to respond.
        deadline = max(utc(case.sla_deadline) if case.sla_deadline else self.queue.now(), self.queue.now() + timedelta(hours=1))
        payload.deadline = deadline
        task = self.queue.schedule(payload, key, PRIORITIES.get(case.priority, 2))
        self.queue.consumer(task, case.id, payload.assessment_ids)
        review = WorkflowReview(id=str(uuid4()), case_id=case.id, task_id=task.id,
            idempotency_key=key, status="OPEN", assigned_role="OPERATIONS_REVIEWER", reason=reason,
            assessment_ids=payload.assessment_ids, evidence_references=payload.evidence_references,
            deadline=deadline, created_at=self.queue.now())
        self.session.add(review)
        self.session.flush()
        self.review_history(review, "orchestrator", "REQUESTED", reason, {"context_fingerprint": self.evidence_stamp(case)})
        self.audit(case, "workflow_review_requested", {"review_id": review.id, "task_id": task.id, "reason": reason})
        return review

    def review_history(self, review, actor, operation, reason, details=None):
        self.session.add(ReviewHistory(id=str(uuid4()), review_id=review.id, actor=actor,
            operation=operation, reason=reason, details={"case_id": review.case_id,
                "assessment_ids": review.assessment_ids, "action_authorization": "NOT_EVALUATED", **(details or {})}, created_at=self.queue.now()))

    def assign_review(self, review_id, identity):
        review = self.session.execute(select(WorkflowReview).where(WorkflowReview.id == review_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if review is None:
            raise LookupError("review_not_found")
        if review.assigned_role not in identity.roles or review.assigned_reviewer not in {None, identity.user_id}:
            raise PermissionError("review_permission_denied")
        if review.status != "OPEN" or utc(review.deadline) <= self.queue.now():
            raise ValueError("review_closed_or_expired")
        if review.assigned_reviewer is None:
            review.assigned_reviewer = identity.user_id
            self.review_history(review, identity.user_id, "ASSIGNED", "Reviewer claimed the workflow review")
            self.session.add(AuditLog(id=str(uuid4()), case_id=review.case_id, entity_type="workflow_review",
                entity_id=review.id, event_type="workflow_review_assigned", summary="Workflow review assigned",
                details={"reviewer": identity.user_id, "role": review.assigned_role, "action_authorization": "NOT_EVALUATED"}))
        return self.finish({"review_id": review.id, "assigned_reviewer": review.assigned_reviewer})

    def decide_review(self, review_id, identity, decision, reason):
        preliminary = self.session.get(WorkflowReview, review_id)
        if preliminary is None:
            raise LookupError("review_not_found")
        case = self.case(preliminary.case_id, lock=True)
        review = self.session.execute(select(WorkflowReview).where(WorkflowReview.id == review_id).with_for_update()
            .execution_options(populate_existing=True)).scalar_one()
        if review.assigned_role not in identity.roles or (review.assigned_reviewer and review.assigned_reviewer != identity.user_id):
            raise PermissionError("review_permission_denied")
        if review.status != "OPEN" or not reason.strip() or utc(review.deadline) <= self.queue.now():
            raise ValueError("review_closed_or_expired")
        current_ids = [item.id for item in self.assessments([case.id])]
        if sorted(current_ids) != sorted(review.assessment_ids):
            raise ValueError("review_assessment_is_stale")
        requested = self.session.execute(select(ReviewHistory).where(ReviewHistory.review_id == review.id,
            ReviewHistory.operation == "REQUESTED").order_by(ReviewHistory.created_at).limit(1)).scalar_one_or_none()
        if requested is None or requested.details.get("context_fingerprint") != self.evidence_stamp(case):
            raise ValueError("review_evidence_or_incident_context_is_stale")
        if case.status != CaseState.AWAITING_HUMAN:
            raise ValueError("case_not_awaiting_human_review")
        if decision not in {"APPROVE", "REJECT", "REQUEST_MORE_INVESTIGATION"}:
            raise ValueError("invalid_review_decision")
        review.status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_MORE_INVESTIGATION": "MORE_INVESTIGATION"}[decision]
        review.decided_at = self.queue.now()
        self.review_history(review, identity.user_id, decision, reason)
        self.audit(case, "workflow_review_decided", {"review_id": review.id, "decision": decision, "actor": identity.user_id,
            "approval_scope": "WORKFLOW_ONLY", "reason": reason})
        for other in self.session.execute(select(WorkflowReview).where(WorkflowReview.case_id == case.id,
            WorkflowReview.id != review.id, WorkflowReview.status == "OPEN").with_for_update()
            .execution_options(populate_existing=True)).scalars():
            other.status = "SUPERSEDED"
            self.review_history(other, identity.user_id, "SUPERSEDED", "Another workflow review decided this case")
            self.audit(case, "workflow_review_superseded", {"review_id": other.id, "decided_review_id": review.id})
        if review.task_id:
            task = self.session.execute(select(WorkTask).where(WorkTask.id == review.task_id).with_for_update()).scalar_one()
            # A human intervention closes a scheduling contract; no fake handler success.
            self.queue.cancel(task, "Human workflow review decided")
        if decision == "APPROVE":
            self._detach_old_work(case, "Workflow approved by human")
            self.transition(case, CaseState.APPROVED, "Human workflow approval; controls not evaluated")
            prepare = self.queue.schedule(self.payload(case, TaskType.PREPARE_EXECUTION, self.assessments([case.id])),
                f"prepare:{case.id}:{review.id}", PRIORITIES.get(case.priority, 2))
            self.queue.consumer(prepare, case.id, review.assessment_ids)
        elif decision == "REJECT":
            self._detach_old_work(case, "Workflow rejected by human")
            self.transition(case, CaseState.BLOCKED, reason)
        else:
            self._detach_old_work(case, "Human requested more investigation")
            case.orchestration_generation += 1
            self.transition(case, CaseState.INVESTIGATION_QUEUED, reason)
            self.schedule_case(case.id, reevaluate=True, commit=False)
        return self.finish({"review_id": review.id, "status": review.status,
            "case_status": case.status.value, "approval_scope": "WORKFLOW_ONLY", "action_authorization": "NOT_EVALUATED"})

    def execute(self, task_id, owner, token):
        # Bound lock/statement waits. No network/LLM work runs in this transaction.
        self.session.execute(text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(self.settings.orchestration_lease_seconds * 1000)})
        preliminary = self.session.get(WorkTask, task_id)
        if preliminary is None:
            raise LookupError("task_not_found")
        # Every handler locks case before task; results and lease completion commit together.
        case = self.case(preliminary.case_id, lock=True)
        task = self.queue.owned(task_id, owner, token)
        if task.task_type not in {"CLASSIFY_CASE", "REEVALUATE_CASE", "ROUTE_CASE", "CHECK_SLA"}:
            raise ValueError("future_handler_unavailable")
        payload = TaskPayload.model_validate(task.payload)
        if payload.case_id != task.case_id or payload.task_type.value != task.task_type:
            raise ValueError("task_payload_identity_mismatch")
        if case.status in TERMINAL_CASES:
            self.queue.cancel(task, "Case no longer eligible")
            return self.finish({"task_id": task.id, "status": task.status})
        if task.task_type in {"CLASSIFY_CASE", "REEVALUATE_CASE"}:
            exceptions = self.session.execute(select(ExceptionRecord.id).where(ExceptionRecord.case_id == case.id)
                .order_by(ExceptionRecord.id).limit(101)).scalars().all()
            if len(exceptions) > 100:
                raise ValueError("case_exception_bound_exceeded")
            classifier = ClassificationService(self.session,
                confirmation_window=timedelta(seconds=self.settings.confirmation_window_seconds),
                workflow_deadline=timedelta(seconds=self.settings.workflow_deadline_seconds), clock=self.queue.now)
            for exception_id in exceptions:
                classifier.evaluate(exception_id, reason="Durable orchestration assessment", commit=False)
            assessments = self.assessments([case.id])
            route = self.queue.schedule(self.payload(case, TaskType.ROUTE_CASE, assessments),
                f"route:{case.id}:{digest([[item.id for item in assessments], case.orchestration_generation, self.evidence_stamp(case)])}",
                PRIORITIES.get(case.priority, 2))
            self.queue.consumer(route, case.id, [item.id for item in assessments])
            result = {"assessment_ids": [item.id for item in assessments], "route_task_id": route.id}
        elif task.task_type == "ROUTE_CASE":
            result = {"scheduled_task_ids": self.route_case(case)}
        else:
            result = self.check_sla(case)
        self.queue.complete(task.id, owner, token, {**result, "action_authorization": "NOT_EVALUATED"})
        return self.finish({"task_id": task.id, "status": "COMPLETED", "result": result})

    def check_sla(self, case):
        now = self.queue.now()
        overdue = case.sla_deadline is not None and utc(case.sla_deadline) <= now
        if overdue and case.status in ROUTABLE_CASES:
            recorded = self.session.execute(select(WorkflowReview.id).where(
                WorkflowReview.idempotency_key == f"review:{case.id}:{case.orchestration_generation}:sla-breach")).scalar_one_or_none()
            if recorded is None:
                self.audit(case, "orchestration_sla_breached", {"deadline": utc(case.sla_deadline).isoformat()})
            self._request_review(case, self.assessments([case.id]), "SLA breached; operational review required", key_suffix="sla-breach")
        elif not overdue:
            self._schedule_sla(case)
        return {"overdue": overdue}

    def poll_cases(self, after_case_id=None, limit=None):
        query = select(Case.id).where(Case.status.in_(list(ROUTABLE_CASES))).order_by(Case.id).limit(
            min(limit or self.settings.orchestration_poll_limit, self.settings.orchestration_poll_limit))
        if after_case_id:
            query = query.where(Case.id > after_case_id)
        ids = self.session.execute(query).scalars().all()
        scheduled = [self.schedule_case(case_id, reevaluate=True)["scheduled"] for case_id in ids]
        return {"case_ids": ids, "scheduled": scheduled, "next_after_case_id": ids[-1] if len(ids) == (limit or self.settings.orchestration_poll_limit) else None}

    def maintenance(self):
        recovered = self.queue.recover()
        expired = self.queue.expire_deadlines()
        self.session.commit()
        from app.execution.service import ExecutionEngine
        ExecutionEngine(self.session, self.settings).reconcile_terminal()
        handled = select(TaskHistory.id).where(TaskHistory.task_id == WorkTask.id,
            TaskHistory.event_type == "task_failure_review_requested").exists()
        failed_ids = self.session.execute(select(WorkTask.id).where(WorkTask.status == "DEAD_LETTER", ~handled)
            .order_by(WorkTask.updated_at, WorkTask.id).limit(self.settings.orchestration_poll_limit)).scalars().all()
        for task_id in failed_ids:
            consumers = self.session.execute(select(TaskConsumer.case_id).where(TaskConsumer.task_id == task_id,
                TaskConsumer.active.is_(True)).order_by(TaskConsumer.case_id).limit(500)).scalars().all()
            for case_id in consumers:
                case = self.case(case_id, lock=True)
                task = self.session.get(WorkTask, task_id)
                if case.status in ROUTABLE_CASES and task.task_type != "REQUEST_HUMAN_REVIEW":
                    self._request_review(case, self.assessments([case.id]), "Durable task failed or timed out", key_suffix=f"failure:{task_id}")
                self.session.commit()
            task = self.session.execute(select(WorkTask).where(WorkTask.id == task_id).with_for_update()).scalar_one()
            self.queue.record(task, "task_failure_review_requested", {"case_ids": consumers})
            self.session.commit()
        reviews = self.session.execute(select(WorkflowReview.id).where(WorkflowReview.status == "OPEN",
            WorkflowReview.deadline <= self.queue.now()).order_by(WorkflowReview.deadline).limit(self.settings.orchestration_poll_limit)).scalars().all()
        for review_id in reviews:
            initial = self.session.get(WorkflowReview, review_id)
            case = self.case(initial.case_id, lock=True)
            review = self.session.execute(select(WorkflowReview).where(WorkflowReview.id == review_id).with_for_update()
                .execution_options(populate_existing=True)).scalar_one()
            if review.status == "OPEN" and utc(review.deadline) <= self.queue.now():
                review.status = "EXPIRED"
                self.review_history(review, "orchestrator", "EXPIRED", "Human review deadline expired")
                self.audit(case, "human_review_deadline_expired", {"review_id": review.id})
                if case.status == CaseState.AWAITING_HUMAN:
                    self.transition(case, CaseState.ESCALATED, "Human review deadline expired")
            self.session.commit()
        return {"leases_recovered": recovered, "task_deadlines_expired": expired, "review_deadlines_examined": len(reviews)}

    def status(self, case_id):
        case = self.case(case_id)
        tasks = self.session.execute(select(WorkTask.status, func.count()).join(TaskConsumer,
            TaskConsumer.task_id == WorkTask.id).where(TaskConsumer.case_id == case_id, TaskConsumer.active.is_(True))
            .group_by(WorkTask.status)).all()
        return {"case_id": case.id, "case_status": case.status.value, "priority": case.priority,
            "workflow_version": WORKFLOW_VERSION, "generation": case.orchestration_generation,
            "task_counts": dict(tasks), "sla_started_at": utc(case.sla_started_at).isoformat() if case.sla_started_at else None,
            "sla_deadline": utc(case.sla_deadline).isoformat() if case.sla_deadline else None,
            "action_authorization": "NOT_EVALUATED", "execution_enabled": False}

    def task_history(self, case_id, limit=100, offset=0):
        self.case(case_id)
        tasks = self.session.execute(select(WorkTask).join(TaskConsumer, TaskConsumer.task_id == WorkTask.id)
            .where(TaskConsumer.case_id == case_id).order_by(WorkTask.created_at.desc(), WorkTask.id)
            .limit(limit).offset(offset)).scalars().all()
        history = self.session.execute(select(TaskHistory).where(TaskHistory.task_id.in_([task.id for task in tasks]))
            .order_by(TaskHistory.created_at, TaskHistory.id).limit(5000)).scalars().all()
        return {"tasks": [self.queue.serialize(task) for task in tasks], "events": [
            {"id": item.id, "task_id": item.task_id, "event_type": item.event_type, "attempt_number": item.attempt_number,
             "details": item.details, "created_at": utc(item.created_at).isoformat()} for item in history]}

    def stats(self):
        now = self.queue.now()
        counts = dict(self.session.execute(select(WorkTask.status, func.count()).group_by(WorkTask.status)).all())
        oldest = self.session.execute(select(func.min(WorkTask.created_at)).where(WorkTask.status.in_(["PENDING", "RETRY_WAIT", "WAITING_HANDLER"]))).scalar_one()
        retries = self.session.execute(select(func.coalesce(func.sum(WorkTask.attempt_count - 1), 0)).where(WorkTask.attempt_count > 1)).scalar_one()
        breaches = self.session.execute(select(func.count(Case.id)).where(Case.sla_deadline <= now,
            Case.status.in_(list(ROUTABLE_CASES)))).scalar_one()
        workers = self.session.execute(select(WorkTask.lease_owner, func.count(), func.max(WorkTask.lease_expires_at)).where(
            WorkTask.status == "RUNNING").group_by(WorkTask.lease_owner).limit(500)).all()
        return {"tasks_by_status": counts, "retry_count": retries, "oldest_queued_at": utc(oldest).isoformat() if oldest else None,
            "oldest_queued_age_seconds": max(0, (now - utc(oldest)).total_seconds()) if oldest else None,
            "active_workers": [{"owner": owner, "running_tasks": count, "last_lease_expiry": utc(expiry).isoformat()} for owner, count, expiry in workers],
            "sla_breaches": breaches, "future_handlers_available": False, "database_queue": "postgresql",
            "workflow_version": WORKFLOW_VERSION}
