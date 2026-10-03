import json
from uuid import uuid4
from sqlalchemy import select, text

from app.controls.service import Controls
from app.controls.models import ControlAuthorization
from app.domain.case_service import CaseState
from app.execution.models import CounterfactualSimulation, ExecutionOperation
from app.execution.simulation import project_confirmation
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import EventRecord
from app.ingestion.schemas import EventEnvelope
from app.models.domain import ActionRecord, VerificationResult
from app.orchestration.contracts import TaskPayload, TaskType
from app.orchestration.models import WorkTask
from app.orchestration.queue import LeaseLost, WorkQueue, digest, utc
from app.orchestration.service import OrchestrationService
from app.simulator.models import SyntheticConfirmationEvent, SyntheticLedgerEntry, SyntheticPayment

EXECUTION_HANDLERS = frozenset({"PREPARE_EXECUTION", "REQUEST_VERIFICATION"})

class ExecutionEngine:
    def __init__(self, session, settings=None):
        self.session = session
        self.workflow = OrchestrationService(session, settings)
        self.controls = Controls(session, self.workflow.settings)
        self.queue = WorkQueue(session, self.workflow.settings, handlers=EXECUTION_HANDLERS)

    def submit(self, authorization_id, identity):
        self.controls.require(identity, "WORKER")
        preliminary = self.session.get(ControlAuthorization, authorization_id)
        if preliminary is None:
            raise LookupError("authorization_not_found")
        case = self.workflow.case(preliminary.case_id, lock=True)
        existing = self.session.scalar(select(ExecutionOperation).where(ExecutionOperation.authorization_id == authorization_id))
        if existing:
            simulation = self.session.scalar(select(CounterfactualSimulation).where(
                CounterfactualSimulation.operation_id == existing.id))
            self.session.commit()
            return {"operation_id": existing.id, "status": existing.status, "action_id": existing.action_id,
                "simulation_id": simulation.id if simulation else None}
        case, authorization, _ = self.controls.current(authorization_id)
        key = digest(["REPLAY_CONFIRMATION", authorization.action["payment_id"]])
        event_id = "resolveos-confirmation-" + key
        projection = project_confirmation(authorization, event_id)
        if projection["outcome"] != "PASS":
            raise ValueError("counterfactual_preflight_blocked")
        conflicting = self.session.scalar(select(ExecutionOperation).where(ExecutionOperation.logical_key == key))
        if conflicting:
            raise ValueError("confirmation_operation_already_registered")
        action = ActionRecord(id=str(uuid4()), case_id=case.id, action_type="REPLAY_CONFIRMATION",
            target=authorization.action["payment_id"], status="QUEUED", payload={"authorization_id": authorization.id})
        self.session.add(action)
        self.session.flush()
        operation = ExecutionOperation(id=str(uuid4()), case_id=case.id, authorization_id=authorization.id,
            action_id=action.id, logical_key=key, status="QUEUED", baseline=authorization.snapshot["source"]["bank"],
            event_id=event_id, created_at=self.queue.now())
        self.session.add(operation)
        self.session.flush()
        simulation = CounterfactualSimulation(id=str(uuid4()), case_id=case.id,
            authorization_id=authorization.id, operation_id=operation.id, outcome=projection["outcome"],
            projection=projection, created_at=self.queue.now())
        self.session.add(simulation)
        self.session.flush()
        payload = self.workflow.payload(case, TaskType.PREPARE_EXECUTION, self.workflow.assessments([case.id]))
        payload.authorization_id, payload.action_id = authorization.id, action.id
        task = self.queue.schedule(payload, "execute:" + operation.id)
        self.queue.consumer(task, case.id, payload.assessment_ids)
        self.workflow.audit(case, "synthetic_execution_scheduled", {"operation_id": operation.id,
            "authorization_id": authorization.id, "action_id": action.id, "actor": identity.user_id,
            "simulation_id": simulation.id, "simulation_outcome": projection["outcome"]})
        self.session.commit()
        return {"operation_id": operation.id, "status": operation.status, "action_id": action.id,
            "task_id": task.id, "simulation_id": simulation.id}

    def preview(self, authorization_id, identity):
        """Persist a hypothetical report. An unapproved action can be previewed, never executed."""
        self.controls.require(identity, "WORKER")
        case, authorization, _ = self.controls.current(authorization_id, require_approval=False)
        key = digest(["REPLAY_CONFIRMATION", authorization.action["payment_id"]])
        projection = project_confirmation(authorization, "resolveos-confirmation-" + key)
        report = CounterfactualSimulation(id=str(uuid4()), case_id=case.id,
            authorization_id=authorization.id, operation_id=None, outcome=projection["outcome"],
            projection=projection, created_at=self.queue.now())
        self.session.add(report)
        self.workflow.audit(case, "counterfactual_preview_created", {"simulation_id": report.id,
            "authorization_id": authorization.id, "outcome": report.outcome, "actor": identity.user_id,
            "reasons": projection["reasons"], "hypothetical_only": True})
        self.session.commit()
        return self.serialize_simulation(report)

    @staticmethod
    def serialize_simulation(report):
        return {"id": report.id, "case_id": report.case_id, "authorization_id": report.authorization_id,
            "operation_id": report.operation_id, "outcome": report.outcome,
            "projection": report.projection, "created_at": report.created_at, "hypothetical_only": True}

    def execute(self, task_id, owner, token, *, fault=None):
        self.session.execute(text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(self.workflow.settings.orchestration_lease_seconds * 1000)})
        preliminary = self.session.get(WorkTask, task_id)
        if preliminary is None:
            raise LookupError("task_not_found")
        payload = TaskPayload.model_validate(preliminary.payload)
        if preliminary.task_type not in EXECUTION_HANDLERS or not payload.authorization_id or not payload.action_id or payload.case_id != preliminary.case_id or payload.task_type.value != preliminary.task_type:
            raise ValueError("bound_execution_handler_required")
        case = self.workflow.case(payload.case_id, lock=True)
        self.workflow._incident_context(case)
        # Check the refreshed fence before reporting authorization/source errors.
        # Keep the final locking fence after controls, preserving lock order.
        fence = self.session.execute(select(WorkTask.status, WorkTask.lease_owner, WorkTask.lease_token,
            WorkTask.lease_expires_at).where(WorkTask.id == task_id)).one()
        if fence.status != "RUNNING" or fence.lease_owner != owner or fence.lease_token != token or not fence.lease_expires_at or utc(fence.lease_expires_at) <= self.queue.now():
            raise LeaseLost("execution_lease_lost")
        operation = self.session.scalar(select(ExecutionOperation).where(ExecutionOperation.action_id == payload.action_id,
            ExecutionOperation.authorization_id == payload.authorization_id, ExecutionOperation.case_id == case.id).with_for_update())
        if operation is None:
            raise LookupError("execution_operation_not_found")
        if payload.task_type == TaskType.PREPARE_EXECUTION:
            _, authorization, _ = self.controls.current(payload.authorization_id)
            simulation = self.session.scalar(select(CounterfactualSimulation).where(
                CounterfactualSimulation.operation_id == operation.id).with_for_update()
                .execution_options(populate_existing=True))
            if simulation is None or simulation.authorization_id != authorization.id or simulation.case_id != case.id:
                raise ValueError("counterfactual_simulation_missing")
            refreshed = project_confirmation(authorization, operation.event_id)
            if simulation.outcome != "PASS" or refreshed["outcome"] != "PASS" or simulation.projection != refreshed:
                raise ValueError("counterfactual_simulation_stale_or_blocked")
        task = self.queue.owned(task_id, owner, token)
        expiry = task.lease_expires_at
        if task.deadline and utc(task.deadline) <= self.queue.now():
            raise LeaseLost("execution_deadline_passed")
        action = self.session.get(ActionRecord, operation.action_id)
        if payload.task_type == TaskType.PREPARE_EXECUTION:
            if operation.status != "QUEUED":
                raise ValueError("execution_operation_not_queued")
            if case.status == CaseState.AWAITING_DECISION:
                self.workflow.transition(case, CaseState.APPROVED, "Deterministic action authorization validated")
            self.workflow.transition(case, CaseState.EXECUTION_QUEUED, "Authorized synthetic operation queued")
            self.workflow.transition(case, CaseState.EXECUTING, "Synthetic confirmation replay started")
            payment = self.session.execute(select(SyntheticPayment.id, SyntheticPayment.correlation_id)
                .where(SyntheticPayment.payment_id == action.target)).one()
            now = self.queue.now()
            confirmation = SyntheticConfirmationEvent(id=str(uuid4()), payment_id=payment.id,
                event_id=operation.event_id, event_type="payment_confirmed", status="CONFIRMED",
                occurred_at=now, correlation_id=payment.correlation_id, is_duplicate=False,
                payload={"origin": "resolveos-synthetic-replay", "action_id": action.id})
            self.session.add(confirmation)
            envelope = EventEnvelope.model_validate({"event_id": operation.event_id, "source_system": "confirmations",
                "event_type": "payment_confirmed", "entity_reference": action.target,
                "correlation_id": payment.correlation_id, "occurred_at": now,
                "schema_version": "1.0", "source_record_reference": operation.event_id,
                "payload": {"confirmation_status": "CONFIRMED", "is_duplicate": False}})
            self.session.add(EventRecord(id=str(uuid4()), **envelope.model_dump(), ingested_at=now,
                processing_status="PENDING", processing_attempts=0, duplicate_receipts=0))
            self.session.flush()
            if fault:
                fault()  # trusted fault injection for atomic crash/expiry tests only
            operation.status, action.status = "VERIFYING", "VERIFYING"
            action.attempt_count += 1
            self.workflow.transition(case, CaseState.VERIFYING, "Effect committed; independent verification required")
            verification = self.workflow.payload(case, TaskType.REQUEST_VERIFICATION, self.workflow.assessments([case.id]))
            verification.authorization_id, verification.action_id = operation.authorization_id, action.id
            followup = self.queue.schedule(verification, "verify:" + operation.id)
            self.queue.consumer(followup, case.id, verification.assessment_ids)
            result = {"outcome": "EFFECT_COMMITTED", "action_id": action.id, "verification_task_id": followup.id}
            self.workflow.audit(case, "synthetic_confirmation_replayed", {"action_id": action.id,
                "authorization_id": operation.authorization_id, "event_id": operation.event_id,
                "simulation_id": simulation.id, "monetary_transfer_repeated": False})
        else:
            if operation.status != "VERIFYING" or case.status != CaseState.VERIFYING:
                raise ValueError("verification_operation_not_eligible")
            # Existing detector consumes this entity within our fenced transaction.
            ExceptionDetectionService(self.session, clock=self.queue.now).run(entity_reference=action.target, commit=False)
            observed, discrepancies = self.verify(operation, action)
            success = not discrepancies
            self.session.add(VerificationResult(id=str(uuid4()), case_id=case.id, action_id=action.id,
                verification_type="INDEPENDENT_SYNTHETIC_CONFIRMATION", success=success, observed_state=observed,
                detail="; ".join(discrepancies) or "Confirmation processed with unchanged monetary state"))
            operation.status = "VERIFIED" if success else "FAILED_VERIFICATION"
            action.status = "VERIFIED" if success else "FAILED_VERIFICATION"
            operation.completed_at = self.queue.now()
            self.workflow.transition(case, CaseState.RESOLVED if success else CaseState.ESCALATED,
                "Independent verification passed" if success else "Independent verification found discrepancies")
            if not success:
                self.workflow._request_review(case, self.workflow.assessments([case.id]),
                    "Independent verification found discrepancies", key_suffix="verification-failure:" + task.id)
            result = {"outcome": operation.status, "action_id": action.id, "discrepancies": discrepancies}
            self.workflow.audit(case, "synthetic_action_verified", result)
        self.queue.owned(task_id, owner, token)  # fence again after all database effects
        task.status, task.result = "COMPLETED", result
        self.queue.clear_lease(task)
        self.queue.record(task, "execution_task_completed", result)
        self.session.flush()
        if utc(expiry) <= self.queue.now():
            raise LeaseLost("execution_lease_expired_before_commit")
        self.session.commit()
        return result

    def reconcile_terminal(self):
        """Recover the durable dead-letter handoff without reversing case/task lock order.

        Queue failure commits first. Reconciliation is repeatable after interruption;
        operation, action, escalation, review and audit commit together.
        """
        ids = self.session.execute(select(WorkTask.id).join(ExecutionOperation,
            ExecutionOperation.action_id == WorkTask.payload["action_id"].as_string()).where(
            WorkTask.status == "DEAD_LETTER", WorkTask.task_type.in_(EXECUTION_HANDLERS),
            ExecutionOperation.status.in_(["QUEUED", "VERIFYING"]))
            .order_by(WorkTask.case_id, WorkTask.id).limit(self.workflow.settings.orchestration_poll_limit)).scalars().all()
        count = 0
        for task_id in ids:
            preliminary = self.session.get(WorkTask, task_id)
            case = self.workflow.case(preliminary.case_id, lock=True)
            self.workflow._incident_context(case)
            task = self.session.execute(select(WorkTask).where(WorkTask.id == task_id)
                .with_for_update().execution_options(populate_existing=True)).scalar_one()
            payload = TaskPayload.model_validate(task.payload)
            operation = self.session.scalar(select(ExecutionOperation).where(
                ExecutionOperation.case_id == case.id, ExecutionOperation.action_id == payload.action_id,
                ExecutionOperation.authorization_id == payload.authorization_id).with_for_update()
                .execution_options(populate_existing=True))
            if task.status != "DEAD_LETTER" or operation is None or operation.status not in {"QUEUED", "VERIFYING"}:
                self.session.commit()
                continue
            expected = "QUEUED" if task.task_type == "PREPARE_EXECUTION" else "VERIFYING"
            if operation.status != expected:
                raise ValueError("terminal_execution_state_inconsistent")
            action = self.session.get(ActionRecord, operation.action_id)
            status = "FAILED_EXECUTION" if expected == "QUEUED" else "VERIFICATION_UNCERTAIN"
            operation.status = action.status = status
            operation.completed_at = self.queue.now()
            self.workflow.transition(case, CaseState.ESCALATED, "Execution task terminated; human assessment required")
            self.workflow._request_review(case, self.workflow.assessments([case.id]),
                "Terminal synthetic execution failure: " + status, key_suffix="execution-failure:" + task.id)
            self.workflow.audit(case, "synthetic_execution_terminal_failure", {
                "task_id": task.id, "action_id": action.id, "authorization_id": operation.authorization_id,
                "status": status, "error_code": task.last_error, "verification_required": expected == "VERIFYING"})
            self.queue.record(task, "execution_failure_reconciled", {"status": status})
            self.session.commit()
            count += 1
        return count

    def verify(self, operation, action):
        payment = self.session.execute(select(SyntheticPayment.id, SyntheticPayment.payment_id, SyntheticPayment.status,
            SyntheticPayment.amount, SyntheticPayment.currency, SyntheticPayment.idempotency_key)
            .where(SyntheticPayment.payment_id == action.target).with_for_update()).mappings().one_or_none()
        discrepancies, ledger, confirmations = [], [], []
        if payment:
            ledger = [dict(row) for row in self.session.execute(select(SyntheticLedgerEntry.ledger_transaction_id,
                SyntheticLedgerEntry.entry_type, SyntheticLedgerEntry.status, SyntheticLedgerEntry.amount, SyntheticLedgerEntry.currency)
                .where(SyntheticLedgerEntry.payment_id == payment["id"]).order_by(SyntheticLedgerEntry.id).limit(1001).with_for_update()).mappings()]
            confirmations = [dict(row) for row in self.session.execute(select(SyntheticConfirmationEvent.event_id,
                SyntheticConfirmationEvent.status).where(SyntheticConfirmationEvent.payment_id == payment["id"])
                .order_by(SyntheticConfirmationEvent.id).limit(1001).with_for_update()).mappings()]
        bank = json.loads(json.dumps({"payment": dict(payment) if payment else None, "ledger": ledger}, default=str))
        if bank["payment"] != operation.baseline["payment"] or bank["ledger"] != operation.baseline["ledger"]:
            discrepancies.append("monetary_source_changed")
        if len(confirmations) != 1 or confirmations[0] != {"event_id": operation.event_id, "status": "CONFIRMED"}:
            discrepancies.append("confirmation_missing_conflicting_or_duplicate")
        simulation = self.session.scalar(select(CounterfactualSimulation).where(
            CounterfactualSimulation.operation_id == operation.id))
        if simulation is None or simulation.outcome != "PASS" or simulation.authorization_id != operation.authorization_id:
            discrepancies.append("counterfactual_simulation_missing_or_invalid")
        else:
            expected = (simulation.projection or {}).get("expected") or {}
            if expected.get("monetary_state_unchanged") != bank or expected.get("additional_payment_count") != 0 or expected.get("additional_ledger_entry_count") != 0:
                discrepancies.append("simulated_monetary_state_diverged")
            if expected.get("confirmation") != {"event_id": operation.event_id, "status": "CONFIRMED"} or expected.get("additional_confirmation_count") != 1:
                discrepancies.append("simulated_confirmation_diverged")
            if expected.get("event_processing_status") != "PROCESSED":
                discrepancies.append("simulated_event_state_invalid")
        event = self.session.scalar(select(EventRecord).where(EventRecord.source_system == "confirmations", EventRecord.event_id == operation.event_id))
        if event is None or event.entity_reference != action.target or event.source_record_reference != operation.event_id or event.payload != {"confirmation_status": "CONFIRMED", "is_duplicate": False} or event.processing_status != "PROCESSED":
            discrepancies.append("confirmation_event_not_verified_processed")
        return {"bank": bank, "confirmations": confirmations, "processing_status": event.processing_status if event else None}, discrepancies
