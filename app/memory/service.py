"""Deterministic publication and bounded retrieval in caller-owned transactions.

Lock order: source Case, OperationalMemory, then MemoryVersion. No commit here:
publication, supersession, review history and audit are one atomic transaction.
"""
from uuid import uuid4
import json

from sqlalchemy import func, select
from app.config import Settings
from app.controls.models import ActionApproval, ActionApprovalHistory, ControlAuthorization
from app.domain.case_service import CaseState
from app.execution.models import ExecutionOperation
from app.ingestion.models import EventRecord
from app.investigation.tools import clean_payload
from app.memory.contracts import CandidateRequest, GOVERNANCE_VERSION, LABEL, MemoryAccess, ReviewRequest
from app.memory.models import MemoryEvidence, MemoryRetrieval, MemoryReview, MemoryVersion, OperationalMemory
from app.models.domain import ActionRecord, AuditLog, Case, Evidence, ExceptionRecord, HumanApproval, Policy, PolicyVersion, VerificationResult
from app.orchestration.queue import digest, utc


class MemoryService:
    def __init__(self, session, settings=None):
        self.session = session
        self.settings = settings or Settings()

    def now(self):
        return self.session.scalar(select(func.clock_timestamp()))

    def require(self, access, case_id, review=False):
        if not isinstance(access, MemoryAccess) or not access.identity.user_id:
            raise PermissionError("memory_identity_required")
        roles = {"OPERATIONS_REVIEWER"} if review else {"WORKER", "OPERATIONS_REVIEWER"}
        if not roles.intersection(access.identity.roles):
            raise PermissionError("memory_role_required")
        if self.settings.environment.lower() not in {"development", "test"} and (access.case_ids is None or access.source_systems is None):
            raise PermissionError("explicit_memory_access_required")
        if access.case_ids is not None and case_id not in access.case_ids:
            raise PermissionError("memory_case_access_denied")

    def case(self, case_id, lock=False):
        query = select(Case).where(Case.id == case_id).execution_options(populate_existing=True)
        case = self.session.scalar(query.with_for_update() if lock else query)
        if case is None:
            raise LookupError("memory_case_not_found")
        return case

    def source(self, case, verification_id):
        """Accept only the actual independent Phase 10 outcome and authorization chain."""
        verification = self.session.scalar(select(VerificationResult).where(
            VerificationResult.id == verification_id).execution_options(populate_existing=True))
        if case.status != CaseState.RESOLVED or verification is None or verification.case_id != case.id or not verification.success or verification.verification_type != "INDEPENDENT_SYNTHETIC_CONFIRMATION":
            raise ValueError("memory_independent_verification_required")
        latest = self.session.scalar(select(VerificationResult.id).where(VerificationResult.case_id == case.id)
            .order_by(VerificationResult.created_at.desc(), VerificationResult.id.desc()).limit(1))
        if latest != verification.id or (verification.observed_state or {}).get("processing_status") != "PROCESSED":
            raise ValueError("memory_verification_corrected_or_incomplete")
        action = self.session.get(ActionRecord, verification.action_id, populate_existing=True)
        operation = self.session.scalar(select(ExecutionOperation).where(
            ExecutionOperation.case_id == case.id, ExecutionOperation.action_id == verification.action_id)
            .execution_options(populate_existing=True))
        if action is None or action.case_id != case.id or action.status != "VERIFIED" or operation is None or operation.status != "VERIFIED" or not operation.completed_at:
            raise ValueError("memory_verified_execution_required")
        authorization = self.session.get(ControlAuthorization, operation.authorization_id, populate_existing=True)
        if authorization is None or authorization.case_id != case.id or authorization.outcome not in {"AUTO_ELIGIBLE", "HUMAN_APPROVAL_REQUIRED"} or authorization.reasons or authorization.policy_version_id is None:
            raise ValueError("memory_action_authorization_required")
        if authorization.fingerprint != digest([authorization.snapshot, authorization.outcome, sorted(set(authorization.reasons))]):
            raise ValueError("memory_authorization_integrity_invalid")
        if action.action_type != authorization.action.get("action_type") or action.target != authorization.action.get("payment_id") or (action.payload or {}).get("authorization_id") != authorization.id:
            raise ValueError("memory_action_binding_invalid")
        if utc(authorization.expires_at) <= utc(operation.created_at):
            raise ValueError("memory_action_authorization_expired_at_submission")
        confirmation_event = self.session.scalar(select(EventRecord).where(EventRecord.source_system == "confirmations",
            EventRecord.event_id == operation.event_id).execution_options(populate_existing=True))
        if confirmation_event is None or confirmation_event.entity_reference != action.target or confirmation_event.source_record_reference != operation.event_id or confirmation_event.processing_status != "PROCESSED" or confirmation_event.payload != {"confirmation_status": "CONFIRMED", "is_duplicate": False}:
            raise ValueError("memory_verification_source_invalid")
        approval_digest = None
        if authorization.outcome == "HUMAN_APPROVAL_REQUIRED":
            approval = self.session.scalar(select(ActionApproval).where(ActionApproval.authorization_id == authorization.id)
                .execution_options(populate_existing=True))
            human = self.session.get(HumanApproval, approval.human_approval_id, populate_existing=True) if approval else None
            history = self.session.scalar(select(ActionApprovalHistory).where(
                ActionApprovalHistory.approval_id == approval.id, ActionApprovalHistory.operation == "APPROVE")
                .order_by(ActionApprovalHistory.created_at.desc()).limit(1)) if approval else None
            if approval is None or approval.status != "APPROVED" or human is None or not human.approved or human.case_id != case.id or human.approver != approval.assigned_user or history is None or history.actor != human.approver or utc(history.created_at) > utc(operation.created_at) or utc(approval.expires_at) <= utc(operation.created_at):
                raise ValueError("memory_human_action_approval_required")
            approval_digest = digest([approval.id, approval.status, human.id, human.approver, human.approved, history.id])
        return verification, action, authorization, {
            "verification": digest([verification.id, verification.success, verification.observed_state, verification.detail,
                verification.created_at, confirmation_event.id, confirmation_event.payload,
                confirmation_event.occurred_at, confirmation_event.ingested_at]),
            "authorization": digest([authorization.id, authorization.fingerprint, authorization.action]),
            "operation": digest([operation.id, operation.status, operation.event_id, operation.completed_at, operation.baseline]),
            "action_approval": approval_digest,
        }

    def evidence(self, case_id, evidence_ids, access):
        if not evidence_ids or len(evidence_ids) > 20:
            raise ValueError("memory_evidence_bounds_invalid")
        # Batch supporting records rather than one query per evidence reference.
        stored = {row.id: row for row in self.session.scalars(select(Evidence)
            .where(Evidence.id.in_(evidence_ids)).execution_options(populate_existing=True))}
        event_ids = [(row.integrity_metadata or {}).get("event_record_id") for row in stored.values()]
        events = {row.id: row for row in self.session.scalars(select(EventRecord)
            .where(EventRecord.id.in_([item for item in event_ids if item])).execution_options(populate_existing=True))}
        entities = set(self.session.scalars(select(ExceptionRecord.source_reference)
            .where(ExceptionRecord.case_id == case_id).limit(101)))
        if len(entities) > 100:
            raise ValueError("memory_source_scope_truncated")
        refs = []
        for evidence_id in sorted(set(evidence_ids)):
            evidence = stored.get(evidence_id)
            event_id = (evidence.integrity_metadata or {}).get("event_record_id") if evidence else None
            event = events.get(event_id)
            if evidence is None or evidence.case_id != case_id or event is None or (evidence.integrity_metadata or {}).get("revoked") or (evidence.integrity_metadata or {}).get("valid") is False or event.processing_status in {"REJECTED", "REVOKED", "FAILED"}:
                raise ValueError("memory_evidence_invalid")
            if access.source_systems is not None and evidence.source_system not in access.source_systems:
                raise PermissionError("memory_source_access_denied")
            if event.entity_reference not in entities or evidence.source_system != event.source_system or evidence.source_record_id != event.source_record_reference or evidence.payload != clean_payload(event.payload) or evidence.relevant_event_timestamp is None or utc(evidence.relevant_event_timestamp) != utc(event.occurred_at):
                raise ValueError("memory_evidence_integrity_invalid")
            fingerprint = digest([evidence.id, evidence.payload, evidence.integrity_metadata,
                evidence.source_system, evidence.source_record_id, evidence.relevant_event_timestamp,
                event.id, event.payload, event.occurred_at, event.ingested_at, event.source_system,
                event.source_record_reference, event.entity_reference])
            refs.append((evidence, event, fingerprint))
        if not refs or len(refs) > 20:
            raise ValueError("memory_evidence_bounds_invalid")
        return refs

    def audit(self, version, actor, operation, reason, previous, replacement=None):
        memory = self.session.get(OperationalMemory, version.memory_id)
        now = self.now()
        version.updated_at = now
        self.session.add(MemoryReview(id=str(uuid4()), version_id=version.id, actor=actor,
            operation=operation, reason=reason, previous_status=previous, new_status=version.status,
            replacement_id=replacement, content_hash=self.content_hash(version), created_at=now))
        self.session.add(AuditLog(id=str(uuid4()), case_id=memory.case_id, entity_type="operational_memory",
            entity_id=version.id, event_type="memory_" + operation.lower(), summary=reason,
            details={"actor": actor, "previous_status": previous, "status": version.status,
                "memory_id": memory.id, "version": version.version, "replacement_id": replacement}))

    def candidate(self, case_id, request, access):
        request = CandidateRequest.model_validate(request)
        self.require(access, case_id)
        case = self.case(case_id, lock=True)
        verification, action, authorization, snapshot = self.source(case, request.verification_id)
        if not self.session.scalar(select(ExceptionRecord.id).where(ExceptionRecord.case_id == case_id,
            ExceptionRecord.exception_type == request.category).limit(1)):
            raise ValueError("memory_category_not_observed")
        refs = self.evidence(case_id, request.evidence_ids, access)
        if any(utc(event.occurred_at) > utc(verification.created_at) or utc(event.ingested_at) > utc(verification.created_at)
               for _, event, _ in refs):
            raise ValueError("memory_evidence_after_verified_outcome")
        existing = self.session.scalar(select(OperationalMemory).where(OperationalMemory.case_id == case_id,
            OperationalMemory.category == request.category))
        if existing:
            raise ValueError("memory_exists_use_correction")
        now = self.now()
        memory = OperationalMemory(id=str(uuid4()), case_id=case_id, category=request.category, created_at=now)
        self.session.add(memory)
        self.session.flush()
        snapshot["evidence_ids"] = [row.id for row, _, _ in refs]
        version = MemoryVersion(id=str(uuid4()), memory_id=memory.id, version=1, category=request.category,
            status="CANDIDATE", summary=request.summary.strip(), failure_pattern=request.failure_pattern,
            resolution_type=action.action_type, verification_id=verification.id, authorization_id=authorization.id,
            policy_version_id=authorization.policy_version_id, governance_version=GOVERNANCE_VERSION,
            trust_snapshot=snapshot, created_at=now, updated_at=now)
        if not version.summary:
            raise ValueError("memory_summary_required")
        self.session.add(version)
        self.session.flush()
        self.session.add_all([MemoryEvidence(version_id=version.id, evidence_id=row.id, event_id=event.id,
            fingerprint=fingerprint) for row, event, fingerprint in refs])
        self.audit(version, access.identity.user_id, "CREATE", "Verified source proposed for human review", "NONE")
        self.session.flush()
        return self.serialize(version)

    def locked(self, version_id, access, review=True):
        preliminary = self.session.get(MemoryVersion, version_id)
        if preliminary is None:
            raise LookupError("memory_version_not_found")
        memory = self.session.get(OperationalMemory, preliminary.memory_id)
        self.require(access, memory.case_id, review=review)
        case = self.case(memory.case_id, lock=True)
        self.session.scalar(select(OperationalMemory).where(OperationalMemory.id == memory.id).with_for_update())
        version = self.session.scalar(select(MemoryVersion).where(MemoryVersion.id == version_id)
            .with_for_update().execution_options(populate_existing=True))
        self.require_version_sources(version, access)
        return case, version

    def require_version_sources(self, version, access):
        if access.source_systems is not None:
            systems = set(self.session.scalars(select(Evidence.source_system).join(MemoryEvidence,
                MemoryEvidence.evidence_id == Evidence.id).where(MemoryEvidence.version_id == version.id).limit(21)))
            if not systems.issubset(access.source_systems):
                raise PermissionError("memory_source_access_denied")

    @staticmethod
    def content_hash(version):
        return digest([version.memory_id, version.version, version.category, version.summary,
            version.failure_pattern, version.resolution_type, version.verification_id,
            version.authorization_id, version.policy_version_id, version.governance_version,
            version.trust_snapshot, version.supersedes_id])

    def valid(self, version, case, access):
        if version.governance_version != GOVERNANCE_VERSION:
            raise ValueError("memory_governance_outdated")
        verification, action, authorization, snapshot = self.source(case, version.verification_id)
        links = self.session.scalars(select(MemoryEvidence).where(MemoryEvidence.version_id == version.id)
            .order_by(MemoryEvidence.evidence_id).limit(21)).all()
        refs = self.evidence(case.id, [link.evidence_id for link in links], access)
        if any(utc(event.occurred_at) > utc(verification.created_at) or utc(event.ingested_at) > utc(verification.created_at)
               for _, event, _ in refs):
            raise ValueError("memory_evidence_after_verified_outcome")
        snapshot["evidence_ids"] = [row.id for row, _, _ in refs]
        memory = self.session.get(OperationalMemory, version.memory_id)
        if not self.session.scalar(select(ExceptionRecord.id).where(ExceptionRecord.case_id == case.id,
            ExceptionRecord.exception_type == version.category).limit(1)):
            raise ValueError("memory_source_category_corrected")
        if memory.case_id != case.id or memory.category != version.category or action.action_type != version.resolution_type or snapshot != version.trust_snapshot or authorization.id != version.authorization_id or authorization.policy_version_id != version.policy_version_id or len(refs) != len(links) or any(link.event_id != event.id or link.fingerprint != fingerprint for link, (_, event, fingerprint) in zip(links, refs)):
            raise ValueError("memory_support_changed")
        if version.status == "ACTIVE":
            approval = self.session.scalar(select(MemoryReview).where(MemoryReview.version_id == version.id,
                MemoryReview.operation == "APPROVE").order_by(MemoryReview.created_at.desc()).limit(1))
            if approval is None or approval.actor != version.reviewer or approval.new_status != "ACTIVE" or approval.content_hash != self.content_hash(version):
                raise ValueError("memory_publication_integrity_invalid")
        return refs

    def review(self, version_id, request, access):
        request = ReviewRequest.model_validate(request)
        if not request.reason.strip():
            raise ValueError("memory_review_reason_required")
        case, version = self.locked(version_id, access)
        previous = version.status
        operation = request.operation
        if operation != "CORRECT" and any(value is not None for value in
            (request.summary, request.failure_pattern, request.verification_id, request.evidence_ids)):
            raise ValueError("memory_correction_operation_required")
        replacement = None
        if operation == "SUBMIT" and previous == "CANDIDATE":
            self.valid(version, case, access)
            version.status = "PENDING_REVIEW"
        elif operation == "APPROVE" and previous == "PENDING_REVIEW":
            self.valid(version, case, access)
            if version.supersedes_id:
                old = self.session.get(MemoryVersion, version.supersedes_id, populate_existing=True)
                if old.status not in {"ACTIVE", "REVOKED", "REJECTED"}:
                    raise ValueError("memory_correction_source_changed")
                old_previous = old.status
                old.status = "SUPERSEDED"
                self.audit(old, access.identity.user_id, "SUPERSEDE", request.reason, old_previous, version.id)
                self.session.flush()  # retire old active before unique-index insertion
            elif self.session.scalar(select(MemoryVersion.id).where(MemoryVersion.memory_id == version.memory_id,
                MemoryVersion.status == "ACTIVE")):
                raise ValueError("memory_active_version_exists")
            version.status, version.reviewer, version.reviewed_at = "ACTIVE", access.identity.user_id, self.now()
        elif operation == "REJECT" and previous in {"CANDIDATE", "PENDING_REVIEW"}:
            version.status = "REJECTED"
        elif operation in {"REVOKE", "WITHDRAW", "FLAG"} and previous == "ACTIVE":
            version.status = "REVOKED"
        elif operation == "FLAG" and previous in {"CANDIDATE", "PENDING_REVIEW"}:
            version.status = "REJECTED"
        elif operation == "CORRECT" and previous in {"CANDIDATE", "PENDING_REVIEW", "ACTIVE", "REVOKED", "REJECTED"}:
            if request.summary is None or not request.summary.strip():
                raise ValueError("memory_corrected_summary_required")
            if (request.verification_id is None) != (request.evidence_ids is None):
                raise ValueError("memory_corrected_source_references_required")
            if request.verification_id is not None:
                verification, action, authorization, snapshot = self.source(case, request.verification_id)
                refs = self.evidence(case.id, request.evidence_ids, access)
                if any(utc(event.occurred_at) > utc(verification.created_at) or utc(event.ingested_at) > utc(verification.created_at)
                       for _, event, _ in refs):
                    raise ValueError("memory_evidence_after_verified_outcome")
                snapshot["evidence_ids"] = [row.id for row, _, _ in refs]
                source_values = dict(verification_id=verification.id, authorization_id=authorization.id,
                    policy_version_id=authorization.policy_version_id, resolution_type=action.action_type,
                    trust_snapshot=snapshot)
                corrected_links = [(row.id, event.id, fingerprint) for row, event, fingerprint in refs]
            else:
                self.valid(version, case, access)
                source_values = {key: getattr(version, key) for key in ("verification_id", "authorization_id",
                    "policy_version_id", "resolution_type", "trust_snapshot")}
                corrected_links = [(link.evidence_id, link.event_id, link.fingerprint) for link in self.session.scalars(
                    select(MemoryEvidence).where(MemoryEvidence.version_id == version.id).limit(21))]
            last = self.session.scalar(select(func.max(MemoryVersion.version)).where(MemoryVersion.memory_id == version.memory_id))
            now = self.now()
            corrected = MemoryVersion(id=str(uuid4()), memory_id=version.memory_id, version=last + 1,
                category=version.category, status="CANDIDATE", summary=request.summary.strip(),
                failure_pattern=request.failure_pattern if request.failure_pattern is not None else version.failure_pattern,
                governance_version=GOVERNANCE_VERSION, **source_values,
                supersedes_id=version.id, created_at=now, updated_at=now)
            self.session.add(corrected)
            self.session.flush()
            for evidence_id, event_id, fingerprint in corrected_links:
                self.session.add(MemoryEvidence(version_id=corrected.id, evidence_id=evidence_id,
                    event_id=event_id, fingerprint=fingerprint))
            replacement = corrected.id
            if previous in {"CANDIDATE", "PENDING_REVIEW"}:
                # A corrected draft is withdrawn from review immediately. The
                # replacement still requires its own submit/approval cycle.
                version.status = "REJECTED"
            self.audit(corrected, access.identity.user_id, "CREATE_CORRECTION", request.reason, "NONE")
        else:
            raise ValueError("memory_transition_not_allowed")
        self.audit(version, access.identity.user_id, operation, request.reason, previous, replacement)
        self.session.flush()
        return {**self.serialize(version), "replacement_id": replacement}

    @staticmethod
    def serialize(version):
        return {key: getattr(version, key) for key in ("id", "memory_id", "version", "category", "status",
            "summary", "failure_pattern", "resolution_type", "verification_id", "authorization_id",
            "policy_version_id", "governance_version", "reviewer", "reviewed_at", "supersedes_id",
            "created_at", "updated_at")}

    def retrieve(self, case_id, category, access, *, top_k=5, context_bytes=8000, source_systems=()):
        self.require(access, case_id)
        self.case(case_id)
        if not isinstance(category, str) or not 1 <= len(category) <= 200 or type(top_k) is not int or not 1 <= top_k <= 10 or type(context_bytes) is not int or not 512 <= context_bytes <= 16000:
            raise ValueError("memory_retrieval_bounds_invalid")
        if not self.session.scalar(select(ExceptionRecord.id).where(ExceptionRecord.case_id == case_id,
            ExceptionRecord.exception_type == category).limit(1)):
            raise PermissionError("memory_category_outside_case")
        query = select(MemoryVersion, OperationalMemory.case_id).join(OperationalMemory,
            OperationalMemory.id == MemoryVersion.memory_id).where(MemoryVersion.category == category,
            MemoryVersion.status == "ACTIVE", OperationalMemory.case_id != case_id)
        if access.case_ids is not None:
            query = query.where(OperationalMemory.case_id.in_(sorted(access.case_ids)))
        # Indexed category/status/time window. No fuzzy scans or vector dependencies.
        candidates = self.session.execute(query.order_by(MemoryVersion.created_at.desc(), MemoryVersion.id.desc())
            .limit(50)).all()
        matches = []
        for version, historical_case_id in candidates:
            self.require(access, historical_case_id)
            try:
                refs = self.valid(version, self.case(historical_case_id), access)
            except PermissionError:
                continue  # inaccessible sources are omitted, never revoked globally
            except ValueError:
                # Fail closed without adding publication locks to read paths. The
                # explicit reconcile operation persists the same invalidation.
                continue
            policy_version = self.session.get(PolicyVersion, version.policy_version_id, populate_existing=True)
            policy = self.session.get(Policy, policy_version.policy_id, populate_existing=True) if policy_version else None
            authorization = self.session.get(ControlAuthorization, version.authorization_id)
            now = self.now()
            current = bool(policy_version and policy and policy_version.is_active and policy.active_version == policy_version.version and policy_version.effective_from and utc(policy_version.effective_from) <= now and authorization.snapshot.get("policy_hash") == digest([policy_version.content, policy_version.version, policy_version.effective_from]))
            # Validate relevant remediation policy including effective_to; policy
            # changes retain historical facts but never certify old guidance.
            if current:
                from app.controls.contracts import ControlPolicy
                from pydantic import ValidationError
                try:
                    current = ControlPolicy.model_validate(policy_version.content).effective_to > now
                except ValidationError:
                    current = False
            systems = sorted({evidence.source_system for evidence, _, _ in refs})
            overlap = len(set(systems).intersection(source_systems))
            verification = self.session.get(VerificationResult, version.verification_id)
            item = {"id": version.id, "memory_id": version.memory_id, "version": version.version,
                "historical_case_id": historical_case_id, "failure_pattern": version.failure_pattern,
                "summary": version.summary, "verified_outcome": "INDEPENDENTLY_VERIFIED_SYNTHETIC_CONFIRMATION",
                "resolution_type": version.resolution_type, "review_status": version.status,
                "reviewer": version.reviewer, "reviewed_at": utc(version.reviewed_at).isoformat(),
                "created_at": utc(version.created_at).isoformat(), "verified_at": utc(verification.created_at).isoformat(),
                "verification_id": version.verification_id, "authorized_action_reference": verification.action_id,
                "policy_version_id": version.policy_version_id, "policy_version": policy_version.version if policy_version else None,
                "guidance_status": "REQUIRES_CURRENT_CONTROLS" if current else "OUTDATED_REMEDIATION_GUIDANCE",
                "evidence_references": [{"evidence_id": evidence.id, "event_record_id": event.id,
                    "source_system": evidence.source_system, "source_record_reference": evidence.source_record_id,
                    "occurred_at": utc(event.occurred_at).isoformat()} for evidence, event, _ in refs],
                "similarity": {"category_match": True, "source_overlap": overlap,
                    "explanation": "Same observed exception category; shared source systems: " + str(overlap)},
                "limitations": ["Similarity does not confirm current causation.",
                    "Reviewer summary is untrusted historical interpretation; query current evidence.",
                    "Every new action requires current independent controls and authorization."]}
            matches.append(item)
        # Stable recency within equal overlap (candidate input is already newest first).
        matches.sort(key=lambda row: -row["similarity"]["source_overlap"])
        result = {"status": "MISSING", "label": LABEL, "action_authorization": "NOT_EVALUATED",
            "evidence": [], "memories": [], "truncated": len(candidates) == 50}
        for item in matches[:top_k]:
            result["memories"].append(item)
            result["status"] = "AVAILABLE"
            if len(json.dumps(result).encode("utf-8")) > context_bytes:
                result["memories"].pop()
                result["status"] = "AVAILABLE" if result["memories"] else "MISSING"
                result["truncated"] = True
                break
        result["truncated"] = result["truncated"] or len(matches) > len(result["memories"])
        self.session.add(MemoryRetrieval(id=str(uuid4()), case_id=case_id, actor=access.identity.user_id,
            category=category, version_ids=[row["id"] for row in result["memories"]],
            limits={"top_k": top_k, "context_bytes": context_bytes, "candidate_limit": 50}, created_at=self.now()))
        self.session.flush()
        return result

    def reconcile(self, version_id, access):
        """Explicit operator invalidation; reads already exclude invalid support."""
        case, version = self.locked(version_id, access)
        if version.status not in {"ACTIVE", "PENDING_REVIEW", "CANDIDATE"}:
            return self.serialize(version)
        try:
            self.valid(version, case, access)
        except ValueError as exc:
            previous = version.status
            version.status = "REVOKED"
            self.audit(version, access.identity.user_id, "INVALIDATE", str(exc), previous)
            self.session.flush()
        return self.serialize(version)
