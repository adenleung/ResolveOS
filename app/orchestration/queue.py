from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.config import Settings, get_settings
from app.models.domain import AuditLog, Case
from app.orchestration.contracts import ACTIVE_TASKS, BUILTIN_TASKS, TaskPayload
from app.orchestration.models import TaskConsumer, TaskHistory, WorkTask


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class LeaseLost(ValueError):
    pass


class WorkQueue:
    """All effects are caller-transactional. Claim/recover transactions must stay short."""
    def __init__(self, session, settings: Settings | None = None, clock=None, handlers=None):
        self.session = session
        self.settings = settings or get_settings()
        self.clock = clock
        from app.investigation.contracts import HANDLERS
        from app.execution.service import EXECUTION_HANDLERS
        live = (self.settings.investigator_live_enabled and self.settings.openai_api_key
                and self.settings.investigator_model and self.settings.investigator_model_version
                and self.settings.investigator_input_cost_per_million > 0
                and self.settings.investigator_output_cost_per_million > 0
                and self.settings.investigator_timeout_seconds < self.settings.orchestration_lease_seconds / 2)
        self.handlers = frozenset(BUILTIN_TASKS) | EXECUTION_HANDLERS | (HANDLERS | {"REQUEST_SUPERVISOR_REVIEW"} if live else frozenset()) | frozenset(handlers or ())

    def now(self):
        # PostgreSQL time is authoritative across worker clocks, including after lock waits.
        if self.clock:
            return utc(self.clock())
        # Reading the clock must not flush an intermediate status/lease combination.
        with self.session.no_autoflush:
            return self.session.execute(select(func.clock_timestamp())).scalar_one()

    def require_postgres(self):
        if self.session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("durable_orchestration_requires_postgresql")

    def record(self, task, operation, details=None):
        now = self.now()
        values = {"task_id": task.id, "incident_id": task.incident_id,
                  "assessment_ids": task.payload.get("assessment_ids", []), **(details or {})}
        self.session.add(TaskHistory(id=str(uuid4()), task_id=task.id, event_type=operation,
            attempt_number=task.attempt_count, details=values, created_at=now))
        self.session.add(AuditLog(id=str(uuid4()), case_id=task.case_id, entity_type="orchestration_task",
            entity_id=task.id, event_type=operation, summary=operation.replace("_", " "), details=values))

    def schedule(self, payload: TaskPayload, identity: str, priority=2, scheduled_at=None):
        self.require_postgres()
        now = self.now()
        status = "PENDING" if payload.task_type.value in self.handlers else "WAITING_HANDLER"
        if payload.task_type.value in {"PREPARE_EXECUTION", "REQUEST_VERIFICATION"} and not (payload.authorization_id and payload.action_id):
            status = "WAITING_HANDLER"
        values = dict(id=str(uuid4()), case_id=payload.case_id, incident_id=payload.incident_id,
            task_type=payload.task_type.value, task_version=payload.task_version,
            workflow_version=payload.workflow_version, status=status, payload=payload.model_dump(mode="json"),
            priority=priority, created_at=now, scheduled_at=utc(scheduled_at or now), deadline=payload.deadline,
            attempt_count=0, max_attempts=self.settings.orchestration_max_attempts, idempotency_key=identity,
            updated_at=now)
        task_id = self.session.execute(insert(WorkTask).values(**values).on_conflict_do_nothing(
            index_elements=[WorkTask.idempotency_key]).returning(WorkTask.id)).scalar_one_or_none()
        task = self.session.get(WorkTask, task_id) if task_id else self.session.execute(
            select(WorkTask).where(WorkTask.idempotency_key == identity).with_for_update()
            .execution_options(populate_existing=True)).scalar_one()
        if task_id:
            self.record(task, "task_created", {"handler_available": status != "WAITING_HANDLER"})
        elif task.status in {"PENDING", "RETRY_WAIT", "WAITING_HANDLER"}:
            if priority < task.priority:
                task.priority = priority
                self.record(task, "task_urgency_updated", {"priority": priority})
            if payload.deadline and (task.deadline is None or utc(payload.deadline) < utc(task.deadline)):
                task.deadline = payload.deadline
                task.payload = {**task.payload, "deadline": utc(payload.deadline).isoformat()}
        return task

    def consumer(self, task, case_id, assessment_ids):
        self.session.execute(insert(TaskConsumer).values(id=str(uuid4()), task_id=task.id, case_id=case_id,
            active=True, assessment_ids=assessment_ids, created_at=self.now()).on_conflict_do_update(
                constraint="uq_task_consumer", set_={"active": True, "assessment_ids": assessment_ids}))

    def claim(self, owner: str, limit=1):
        self.require_postgres()
        if not owner.strip() or len(owner) > 100:
            raise ValueError("invalid_lease_owner")
        now = self.now()
        cap = min(max(limit, 1), self.settings.orchestration_poll_limit)
        eligible = select(WorkTask).where(
            WorkTask.status.in_(["PENDING", "RETRY_WAIT"]), WorkTask.task_type.in_(self.handlers),
            WorkTask.scheduled_at <= now, WorkTask.attempt_count < WorkTask.max_attempts,
            or_(WorkTask.deadline.is_(None), WorkTask.deadline > now),
            or_(WorkTask.task_type.not_in(["PREPARE_EXECUTION", "REQUEST_VERIFICATION"]),
                and_(WorkTask.payload["authorization_id"].as_string().is_not(None),
                     WorkTask.payload["action_id"].as_string().is_not(None))),
        )
        tasks = self.session.execute(eligible.where(
            WorkTask.created_at <= now - timedelta(seconds=self.settings.orchestration_fairness_seconds))
            .order_by(WorkTask.created_at, WorkTask.id).limit(cap).with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)).scalars().all()
        if len(tasks) < cap:
            tasks.extend(self.session.execute(eligible.where(WorkTask.id.not_in([task.id for task in tasks]))
                .order_by(WorkTask.priority, WorkTask.scheduled_at, WorkTask.created_at, WorkTask.id)
                .limit(cap - len(tasks)).with_for_update(skip_locked=True).execution_options(populate_existing=True)).scalars().all())
        claimed = []
        for task in tasks:
            task.status = "RUNNING"
            task.attempt_count += 1
            task.lease_owner = owner
            task.lease_token = str(uuid4())
            task.lease_expires_at = now + timedelta(seconds=self.settings.orchestration_lease_seconds)
            task.updated_at = now
            self.record(task, "task_claimed", {"owner": owner, "expires_at": task.lease_expires_at.isoformat()})
            claimed.append(self.serialize(task, include_lease=True))
        self.session.flush()
        return claimed

    def owned(self, task_id, owner, token):
        task = self.session.execute(select(WorkTask).where(WorkTask.id == task_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if task is None:
            raise LookupError("task_not_found")
        if task.status != "RUNNING" or task.lease_owner != owner or task.lease_token != token or utc(task.lease_expires_at) <= self.now():
            raise LeaseLost("task_lease_lost")
        return task

    def renew(self, task_id, owner, token):
        task = self.owned(task_id, owner, token)
        task.lease_expires_at = self.now() + timedelta(seconds=self.settings.orchestration_lease_seconds)
        task.updated_at = self.now()
        self.record(task, "task_lease_renewed", {"owner": owner})
        self.session.flush()
        return self.serialize(task, include_lease=True)

    def clear_lease(self, task):
        task.lease_owner = task.lease_token = task.lease_expires_at = None
        task.updated_at = self.now()

    def complete(self, task_id, owner, token, result):
        task = self.owned(task_id, owner, token)
        if task.task_type not in BUILTIN_TASKS:
            raise ValueError("future_handler_unavailable")
        task.status = "COMPLETED"
        task.result = result
        self.clear_lease(task)
        self.record(task, "task_completed", {"result": result})
        self.session.flush()
        return task

    def fail(self, task_id, owner, token, error_code, transient=True):
        task = self.owned(task_id, owner, token)
        self._failure(task, error_code, transient)
        self.session.flush()
        return self.serialize(task)

    def _failure(self, task, error_code, transient):
        task.last_error = error_code[:1000]
        deadline_passed = task.deadline is not None and utc(task.deadline) <= self.now()
        retry = transient and task.attempt_count < task.max_attempts and not deadline_passed
        self.clear_lease(task)
        if retry:
            delay = min(self.settings.orchestration_backoff_seconds * 2 ** max(0, task.attempt_count - 1),
                        self.settings.orchestration_backoff_cap_seconds)
            task.scheduled_at = self.now() + timedelta(seconds=delay)
            task.status = "RETRY_WAIT"
            self.record(task, "task_retry_scheduled", {"error_code": task.last_error, "scheduled_at": task.scheduled_at.isoformat()})
        else:
            task.status = "DEAD_LETTER"
            self.record(task, "task_failed", {"error_code": task.last_error, "terminal": True})

    def recover(self, limit=None):
        self.require_postgres()
        now = self.now()
        tasks = self.session.execute(select(WorkTask).where(WorkTask.status == "RUNNING",
            WorkTask.lease_expires_at <= now).order_by(WorkTask.lease_expires_at, WorkTask.id)
            .limit(limit or self.settings.orchestration_poll_limit).with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)).scalars().all()
        for task in tasks:
            self.record(task, "task_lease_expired")
            self._failure(task, "worker_lease_expired", True)
        self.session.flush()
        return len(tasks)

    def expire_deadlines(self, limit=None):
        tasks = self.session.execute(select(WorkTask).where(WorkTask.status.in_(ACTIVE_TASKS),
            WorkTask.deadline <= self.now()).order_by(WorkTask.deadline, WorkTask.id)
            .limit(limit or self.settings.orchestration_poll_limit).with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)).scalars().all()
        for task in tasks:
            self._failure(task, "task_deadline_expired", False)
        self.session.flush()
        return len(tasks)

    def cancel(self, task, reason):
        if task.status in ACTIVE_TASKS:
            task.status = "CANCELLED"
            self.clear_lease(task)
            self.record(task, "task_cancelled", {"reason": reason})

    def requeue(self, task_id, reason, max_attempts):
        preliminary = self.session.get(WorkTask, task_id)
        if preliminary is None:
            raise LookupError("task_not_found")
        case = self.session.execute(select(Case).where(Case.id == preliminary.case_id).with_for_update()
            .execution_options(populate_existing=True)).scalar_one()
        task = self.session.execute(select(WorkTask).where(WorkTask.id == task_id).with_for_update()
            .execution_options(populate_existing=True)).scalar_one_or_none()
        if task is None:
            raise LookupError("task_not_found")
        if task.status != "DEAD_LETTER" or task.task_type not in self.handlers or not reason.strip():
            raise ValueError("task_not_eligible_for_requeue")
        if case.status.value in {"RESOLVED", "FAILED", "BLOCKED", "ESCALATED", "EXECUTING", "VERIFYING", "APPROVED", "EXECUTION_QUEUED"}:
            raise ValueError("case_not_eligible_for_requeue")
        if not task.attempt_count < max_attempts <= 10 or (task.deadline and utc(task.deadline) <= self.now()):
            raise ValueError("retry_budget_or_deadline_exhausted")
        task.max_attempts = max_attempts
        task.status = "PENDING"
        task.scheduled_at = self.now()
        task.updated_at = self.now()
        self.record(task, "task_requeued", {"reason": reason, "max_attempts": max_attempts})
        self.session.flush()
        return self.serialize(task)

    def serialize(self, task, include_lease=False):
        result = {name: getattr(task, name) for name in ("id", "case_id", "incident_id", "task_type", "task_version",
            "workflow_version", "status", "priority", "attempt_count", "max_attempts", "last_error", "result")}
        result.update({name: utc(getattr(task, name)).isoformat() if getattr(task, name) else None
            for name in ("created_at", "scheduled_at", "deadline", "lease_expires_at", "updated_at")})
        result["handler_available"] = task.task_type in self.handlers
        if task.task_type in {"PREPARE_EXECUTION", "REQUEST_VERIFICATION"}:
            result["handler_available"] = bool(task.payload.get("authorization_id") and task.payload.get("action_id"))
        if include_lease:
            result.update(lease_owner=task.lease_owner, lease_token=task.lease_token, payload=task.payload)
            result["payload"] = {**task.payload, "attempt_number": task.attempt_count}
        return result
