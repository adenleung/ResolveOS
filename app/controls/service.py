"""No AI decision, workflow approval or request field can grant authorization."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import select, func

from app.controls.contracts import ActionRequest, ControlPolicy
from app.controls.models import ActionApproval, ActionApprovalHistory, ControlAuthorization
from app.domain.case_service import CaseState
from app.ingestion.models import EventRecord
from app.investigation.tools import clean_payload
from app.models.domain import CaseIncident, Decision, Evidence, ExceptionRecord, HumanApproval, Policy, PolicyVersion
from app.orchestration.queue import digest, utc
from app.orchestration.service import OrchestrationService
from app.simulator.models import SyntheticConfirmationEvent, SyntheticLedgerEntry, SyntheticPayment
from app.supervisor.models import SupervisorReview

class Controls:
    def __init__(self, session, settings=None, *, read_only=False):
        self.session = session
        self.workflow = OrchestrationService(session, settings)
        self.read_only = read_only

    def lock(self, statement):
        return statement if self.read_only else statement.with_for_update()

    @staticmethod
    def amount(value):
        try:
            parsed = Decimal(str(value))
            return parsed if parsed.is_finite() else Decimal(0)
        except InvalidOperation:
            return Decimal(0)

    @staticmethod
    def require(identity, role):
        if not identity.user_id or role not in identity.roles:
            raise PermissionError("control_permission_required")

    def policy(self, version_id):
        version = self.session.execute(self.lock(select(PolicyVersion).where(PolicyVersion.id == version_id))
            .execution_options(populate_existing=True)).scalar_one_or_none()
        if version is None:
            return None, None, ["policy_missing"]
        policy = self.session.execute(self.lock(select(Policy).where(Policy.id == version.policy_id))
            .execution_options(populate_existing=True)).scalar_one()
        try:
            rules = ControlPolicy.model_validate(version.content)
        except ValidationError:
            return version, None, ["policy_schema_invalid"]
        now = self.workflow.queue.now()
        if not version.is_active or policy.active_version != version.version or not version.effective_from or utc(version.effective_from) > now or rules.effective_to <= now:
            return version, rules, ["policy_inactive_or_expired"]
        return version, rules, []

    def observe(self, case, action):
        entities = self.session.execute(select(ExceptionRecord.source_reference).where(ExceptionRecord.case_id == case.id)).scalars().all()
        issues = []
        if action.payment_id not in entities:
            issues.append("payment_outside_case")
        now = self.workflow.queue.now()
        rows = self.session.execute(select(EventRecord).where(EventRecord.entity_reference == action.payment_id,
            EventRecord.occurred_at <= now, EventRecord.ingested_at <= now)
            .order_by(EventRecord.occurred_at, EventRecord.ingested_at, EventRecord.id).limit(1001)).scalars().all()
        if len(rows) > 1000:
            issues.append("source_window_truncated")
        current = {}
        for row in rows[:1000]:
            current[(row.source_system, row.source_record_reference)] = row
        observed = [{"id": row.id, "source_system": row.source_system, "source_record_reference": row.source_record_reference,
            "occurred_at": utc(row.occurred_at).isoformat(), "ingested_at": utc(row.ingested_at).isoformat(),
            "payload": clean_payload(row.payload)} for row in current.values()]
        payments = [row.payload for row in current.values() if row.source_system == "payments"]
        ledgers = [row.payload for row in current.values() if row.source_system == "ledger"]
        confirmations = [row.payload for row in current.values() if row.source_system == "confirmations"]
        # Explicit columns only: runtime controls never load simulator labels/ground truth.
        payment = self.session.execute(self.lock(select(SyntheticPayment.id, SyntheticPayment.payment_id,
            SyntheticPayment.status, SyntheticPayment.amount, SyntheticPayment.currency, SyntheticPayment.idempotency_key)
            .where(SyntheticPayment.payment_id == action.payment_id))).mappings().one_or_none()
        bank_ledger, bank_confirmation = [], []
        if payment:
            bank_ledger = [dict(row) for row in self.session.execute(self.lock(select(SyntheticLedgerEntry.ledger_transaction_id,
                SyntheticLedgerEntry.entry_type, SyntheticLedgerEntry.status, SyntheticLedgerEntry.amount, SyntheticLedgerEntry.currency)
                .where(SyntheticLedgerEntry.payment_id == payment["id"]).order_by(SyntheticLedgerEntry.id)
                .limit(1001))).mappings()]
            bank_confirmation = [dict(row) for row in self.session.execute(self.lock(select(SyntheticConfirmationEvent.event_id,
                SyntheticConfirmationEvent.status).where(SyntheticConfirmationEvent.payment_id == payment["id"])
                .order_by(SyntheticConfirmationEvent.id).limit(1001))).mappings()]
        if not payment or len(payments) != 1:
            issues.append("payment_source_missing_or_ambiguous")
        if not ledgers or not bank_ledger:
            issues.append("ledger_evidence_missing")
        if len(bank_ledger) > 1000 or len(bank_confirmation) > 1000:
            issues.append("bank_source_truncated")
        if payment and payments:
            observed_payment = payments[0]
            if payment["status"] != "SETTLED" or observed_payment.get("payment_status") != "SETTLED":
                issues.append("payment_not_settled")
            if self.amount(observed_payment.get("amount", 0)) != payment["amount"] or observed_payment.get("currency") != payment["currency"] or observed_payment.get("idempotency_key") != payment["idempotency_key"]:
                issues.append("payment_source_disagreement")
            debits = [row for row in bank_ledger if row["entry_type"] == "DEBIT" and row["status"] == "POSTED"]
            observed_debits = [row for row in ledgers if row.get("entry_type") == "DEBIT" and row.get("ledger_status") == "POSTED"]
            if len(debits) != 1 or len(observed_debits) != 1:
                issues.append("duplicate_or_missing_debit")
            elif debits[0]["amount"] != payment["amount"] or debits[0]["currency"] != payment["currency"] or self.amount(observed_debits[0].get("amount", 0)) != payment["amount"] or observed_debits[0].get("currency") != payment["currency"] or observed_debits[0].get("ledger_transaction_id") != debits[0]["ledger_transaction_id"]:
                issues.append("ledger_payment_disagreement")
            if len([row for row in bank_ledger if row["entry_type"] == "CREDIT"]) > 1 or any(
                row["entry_type"] not in {"DEBIT", "CREDIT"} or row["status"] != "POSTED" or
                row["amount"] != payment["amount"] or row["currency"] != payment["currency"] for row in bank_ledger):
                issues.append("ledger_effects_uncertain")
            duplicate_entities = self.session.execute(select(EventRecord.entity_reference).where(
                EventRecord.source_system == "payments", EventRecord.payload["idempotency_key"].as_string() == payment["idempotency_key"])
                .distinct().limit(2)).scalars().all()
            if any(entity != action.payment_id for entity in duplicate_entities):
                issues.append("duplicate_payment_identity")
        if any(row.get("confirmation_status") == "CONFIRMED" for row in confirmations) or any(row["status"] == "CONFIRMED" for row in bank_confirmation):
            issues.append("confirmation_already_present")
        if bank_confirmation:
            # Pending/conflicting confirmations require investigation, never blind replay.
            issues.append("confirmation_state_uncertain")
        incident = self.session.scalar(select(CaseIncident.incident_id).where(CaseIncident.case_id == case.id, CaseIncident.removed_at.is_(None)))
        affected = self.session.scalar(select(func.count()).select_from(CaseIncident).where(
            CaseIncident.incident_id == incident, CaseIncident.removed_at.is_(None))) if incident else 1
        bank = {"payment": dict(payment) if payment else None, "ledger": bank_ledger, "confirmations": bank_confirmation}
        # JSON must retain Decimal values as strings, with stable hashing.
        import json
        bank = json.loads(json.dumps(bank, default=str))
        return {"events": observed, "bank": bank, "affected_cases": affected,
                "evidence_stamp": self.workflow.evidence_stamp(case)}, issues

    def snapshot(self, case, review, action, version, rules):
        source, issues = self.observe(case, action)
        now = self.workflow.queue.now()
        if case.status not in {CaseState.AWAITING_DECISION, CaseState.APPROVED}:
            issues.append("case_state_not_eligible")
        assessments = sorted(row.id for row in self.workflow.assessments([case.id]))
        if review.case_id != case.id or review.outcome != "RECOMMENDATION" or review.result.get("action_authorization") != "NOT_EVALUATED":
            issues.append("supervisor_not_eligible")
        if review.result.get("proposed_action") != action.action_type:
            issues.append("action_not_recommended")
        if review.snapshot.get("generation") != case.orchestration_generation or sorted(review.snapshot.get("assessment_ids", [])) != assessments or review.snapshot.get("evidence_stamp") != source["evidence_stamp"]:
            issues.append("supervisor_snapshot_stale")
        if review.result.get("unresolved_issues") or review.snapshot.get("issues") or not review.result.get("supported_conclusions"):
            issues.append("unresolved_or_unsupported_recommendation")
        evidence_ids = review.result.get("evidence_ids", [])
        if not evidence_ids:
            issues.append("supervisor_evidence_missing")
        source_ids = {row["id"] for row in source["events"]}
        for ref in evidence_ids:
            stored = self.session.get(Evidence, ref)
            if stored is None or stored.case_id != case.id or (stored.integrity_metadata or {}).get("event_record_id") not in source_ids:
                issues.append("case_evidence_missing_or_stale")
                continue
            row = next(row for row in source["events"] if row["id"] == stored.integrity_metadata["event_record_id"])
            if stored.payload != row["payload"] or stored.source_system != row["source_system"] or stored.source_record_id != row["source_record_reference"] or not stored.relevant_event_timestamp or utc(stored.relevant_event_timestamp).isoformat() != row["occurred_at"]:
                issues.append("case_evidence_integrity_failed")
        for finding in review.result.get("supported_conclusions", []):
            refs = finding.get("evidence_ids", [])
            field = finding.get("field")
            if not refs or not field or not set(refs).issubset(evidence_ids) or finding.get("assessment") != "SUPPORTED":
                issues.append("supervisor_conclusion_not_supported")
                continue
            for ref in refs:
                stored = self.session.get(Evidence, ref)
                if stored is None or field not in stored.payload or type(stored.payload[field]) is not type(finding.get("expected_value")) or stored.payload[field] != finding.get("expected_value"):
                    issues.append("supervisor_predicate_not_supported")
        payment = source["bank"]["payment"]
        if rules and payment:
            amount = Decimal(payment["amount"])
            if action.action_type not in rules.action_allowlist or amount <= 0 or amount > rules.max_amount or payment["currency"] != rules.currency:
                issues.append("policy_action_or_amount_limit")
            if source["affected_cases"] > rules.max_affected_cases or rules.max_blast_radius < 1:
                issues.append("policy_blast_radius_limit")
        return {"case_id": case.id, "case_state": case.status.value, "generation": case.orchestration_generation, "assessment_ids": assessments,
            "source": source, "review_id": review.id, "review_hash": digest([review.snapshot, review.result]),
            "policy_id": version.id if version else None,
            "policy_hash": digest([version.content, version.version, version.effective_from]) if version else None,
            "action": action.model_dump()}, sorted(set(issues))

    def inspect(self, case_id, review_id, version_id, action, identity):
        """Shared deterministic calculation. Read-only callers acquire no row locks."""
        if self.read_only:
            if not identity.user_id or not identity.roles.intersection({"WORKER", "OPERATIONS_REVIEWER"}):
                raise PermissionError("shadow_read_permission_required")
        else:
            self.require(identity, "WORKER")
        action = ActionRequest.model_validate(action)
        case = self.workflow.case(case_id, lock=not self.read_only)
        if not self.read_only:
            self.workflow._incident_context(case)  # operational lock order is preserved
        review = self.session.get(SupervisorReview, review_id)
        if review is None:
            raise LookupError("supervisor_review_not_found")
        version, rules, policy_issues = self.policy(version_id)
        snapshot, issues = self.snapshot(case, review, action, version, rules)
        issues.extend(policy_issues)
        amount = Decimal(snapshot["source"]["bank"]["payment"]["amount"]) if snapshot["source"]["bank"]["payment"] else Decimal(0)
        severe = {"source_window_truncated", "bank_source_truncated", "policy_blast_radius_limit"}
        outcome = "ESCALATED" if severe.intersection(issues) else ("BLOCKED" if issues else
            ("HUMAN_APPROVAL_REQUIRED" if rules.human_approval_required or amount > rules.automatic_amount_limit else "AUTO_ELIGIBLE"))
        return case, review, version, rules, action, snapshot, issues, outcome

    def evaluate(self, case_id, review_id, version_id, action, identity):
        if self.read_only:
            raise PermissionError("read_only_controls_cannot_authorize")
        case, review, version, rules, action, snapshot, issues, outcome = self.inspect(case_id, review_id, version_id, action, identity)
        fingerprint = digest([snapshot, outcome, sorted(set(issues))])
        existing = self.session.scalar(select(ControlAuthorization).where(ControlAuthorization.fingerprint == fingerprint))
        if existing:
            self.session.commit()
            return self.serialize(existing)
        now = self.workflow.queue.now()
        decision = Decision(id=str(uuid4()), case_id=case.id, decision_type="SYNTHETIC_ACTION_CONTROL",
            decision=outcome, rationale="; ".join(issues) or "Deterministic synthetic policy and source preconditions satisfied")
        self.session.add(decision)
        self.session.flush()
        record = ControlAuthorization(id=str(uuid4()), case_id=case.id, supervisor_review_id=review.id,
            policy_version_id=version.id if version else None, decision_id=decision.id, fingerprint=fingerprint,
            outcome=outcome, action=action.model_dump(), snapshot=snapshot, reasons=sorted(set(issues)), created_at=now,
            expires_at=now + timedelta(seconds=rules.authorization_ttl_seconds if rules else 60))
        self.session.add(record)
        self.session.flush()
        if outcome == "HUMAN_APPROVAL_REQUIRED":
            self.session.add(ActionApproval(id=str(uuid4()), authorization_id=record.id,
                assigned_role=rules.approval_role, status="OPEN", created_at=now,
                expires_at=min(record.expires_at, now + timedelta(seconds=rules.approval_ttl_seconds))))
        self.workflow.audit(case, "control_evaluated", {"authorization_id": record.id, "policy_version_id": record.policy_version_id,
            "control_outcome": outcome, "action": record.action, "reasons": record.reasons, "actor": identity.user_id})
        self.session.commit()
        return self.serialize(record)

    def current(self, authorization_id, *, require_approval=True):
        if self.read_only:
            raise PermissionError("read_only_controls_cannot_authorize")
        preliminary = self.session.get(ControlAuthorization, authorization_id)
        if preliminary is None:
            raise LookupError("authorization_not_found")
        case = self.workflow.case(preliminary.case_id, lock=True)
        self.workflow._incident_context(case)
        record = self.session.execute(select(ControlAuthorization).where(ControlAuthorization.id == authorization_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one()
        if record.outcome not in {"AUTO_ELIGIBLE", "HUMAN_APPROVAL_REQUIRED"} or record.expires_at <= self.workflow.queue.now():
            raise ValueError("authorization_blocked_or_expired")
        version, rules, issues = self.policy(record.policy_version_id)
        review = self.session.get(SupervisorReview, record.supervisor_review_id)
        if review is None:
            raise ValueError("authorization_review_missing")
        snapshot, source_issues = self.snapshot(case, review, ActionRequest.model_validate(record.action), version, rules)
        if issues or source_issues or digest(snapshot) != digest(record.snapshot):
            raise ValueError("authorization_stale")
        if require_approval and record.outcome == "HUMAN_APPROVAL_REQUIRED":
            approval = self.session.execute(select(ActionApproval).where(ActionApproval.authorization_id == record.id)
                .with_for_update().execution_options(populate_existing=True)).scalar_one()
            human = self.session.get(HumanApproval, approval.human_approval_id) if approval.human_approval_id else None
            if approval.assigned_role != rules.approval_role or approval.status != "APPROVED" or approval.expires_at <= self.workflow.queue.now() or human is None or not human.approved or human.case_id != case.id or human.approver != approval.assigned_user:
                raise ValueError("action_approval_required_or_stale")
        return case, record, rules

    def approve(self, approval_id, identity, operation, reason):
        if self.read_only:
            raise PermissionError("read_only_controls_cannot_approve")
        if operation not in {"APPROVE", "REJECT", "MORE_INVESTIGATION", "REVOKE"} or not reason.strip() or len(reason) > 1000:
            raise ValueError("invalid_action_approval_operation")
        preliminary = self.session.get(ActionApproval, approval_id)
        if preliminary is None:
            raise LookupError("action_approval_not_found")
        self.require(identity, preliminary.assigned_role)
        case, authorization, _ = self.current(preliminary.authorization_id, require_approval=False)
        approval = self.session.execute(select(ActionApproval).where(ActionApproval.id == approval_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one()
        if approval.assigned_user and approval.assigned_user != identity.user_id:
            raise PermissionError("action_approval_assignee_mismatch")
        if approval.expires_at <= self.workflow.queue.now() or (approval.status != "OPEN" and not (operation == "REVOKE" and approval.status == "APPROVED")):
            raise ValueError("action_approval_closed_or_expired")
        approval.assigned_user = identity.user_id
        approval.status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "MORE_INVESTIGATION": "MORE_INVESTIGATION", "REVOKE": "REVOKED"}[operation]
        if operation in {"APPROVE", "REJECT"}:
            human = HumanApproval(id=str(uuid4()), case_id=case.id, approver=identity.user_id,
                approved=operation == "APPROVE", rationale=reason)
            self.session.add(human)
            self.session.flush()
            approval.human_approval_id = human.id
        self.session.add(ActionApprovalHistory(id=str(uuid4()), approval_id=approval.id, actor=identity.user_id,
            operation=operation, reason=reason, created_at=self.workflow.queue.now()))
        self.workflow.audit(case, "action_approval_" + operation.lower(), {"approval_id": approval.id,
            "authorization_id": authorization.id, "policy_version_id": authorization.policy_version_id, "actor": identity.user_id})
        if operation == "MORE_INVESTIGATION":
            self.workflow._request_review(case, self.workflow.assessments([case.id]), "Action approval requires further investigation")
        self.session.commit()
        return {"approval_id": approval.id, "status": approval.status}

    @staticmethod
    def serialize(record):
        return {key: getattr(record, key) for key in ("id", "case_id", "supervisor_review_id", "policy_version_id",
            "outcome", "action", "reasons", "fingerprint", "created_at", "expires_at")}
