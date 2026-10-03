"""Actual PostgreSQL publication, independent execution provenance and concurrency."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_phase6_postgres import postgres_engine
from test_phase9_postgres import fixture_case, WORKER, REVIEWER
from test_phase10_postgres import queued, claim, execute
from test_phase7_postgres import FakeModel, prepare, output
from app.config import Settings
from app.database import DatabaseManager
from app.domain.case_service import CaseState
from app.execution.models import ExecutionOperation
from app.ingestion.models import EventRecord
from app.investigation.contracts import HANDLERS, ModelTurn, ToolCall
from app.investigation.service import InvestigationRunner
from app.investigation.tools import ToolDenied, ToolDispatcher
from app.investigation.validation import EvidenceRejected, validate_output
from app.memory.contracts import LABEL, MemoryAccess
from app.memory.models import MemoryEvidence, MemoryRetrieval, MemoryReview, MemoryVersion, OperationalMemory
from app.memory.service import MemoryService
from app.models.domain import ActionRecord, AuditLog, Case, Evidence, ExceptionRecord, HumanApproval, Policy, PolicyVersion, VerificationResult
from app.orchestration.auth import Identity
from app.orchestration.contracts import TaskType
from app.orchestration.models import WorkTask
from app.orchestration.queue import WorkQueue
from app.orchestration.service import OrchestrationService

CATEGORY = "PAYMENT_CONFIRMATION_MISMATCH"
WORK_ACCESS = MemoryAccess(WORKER)
REVIEW_ACCESS = MemoryAccess(REVIEWER)


@pytest.fixture
def session(postgres_engine):
    # Existing global fixture safely clears all tables, including FK-linked memory.
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as value:
        yield value
        value.rollback()


@pytest.fixture
def settings():
    return Settings(environment="test", orchestration_lease_seconds=30)


def resolved(session, settings, human=False):
    parts, authorization, submitted, database = queued(session, settings, human)
    assert execute(database, settings, claim(session, settings))["outcome"] == "EFFECT_COMMITTED"
    assert execute(database, settings, claim(session, settings))["outcome"] == "VERIFIED"
    session.expire_all()
    verification = session.scalar(select(VerificationResult).where(VerificationResult.case_id == parts[0].id))
    evidence = session.scalar(select(Evidence).where(Evidence.case_id == parts[0].id))
    request = dict(category=CATEGORY, verification_id=verification.id,
        summary="Settled payment had a missing confirmation; authorized replay was independently verified.",
        failure_pattern="Missing confirmation with one posted debit", evidence_ids=[evidence.id])
    return parts, request


def candidate(session, settings, human=False):
    parts, request = resolved(session, settings, human)
    record = MemoryService(session, settings).candidate(parts[0].id, request, WORK_ACCESS)
    session.commit()
    return parts, request, record


def transition(session, settings, version_id, operation, access=REVIEW_ACCESS, **kwargs):
    result = MemoryService(session, settings).review(version_id,
        dict(operation=operation, reason="Reviewed against source records", **kwargs), access)
    session.commit()
    return result


def publish(session, settings, human=False):
    parts, request, record = candidate(session, settings, human)
    transition(session, settings, record["id"], "SUBMIT")
    transition(session, settings, record["id"], "APPROVE")
    return parts, request, record


def new_case(session, category=CATEGORY):
    case = Case(id=uuid4().hex, case_number="MEM-" + uuid4().hex, status=CaseState.DETECTED)
    session.add(case)
    session.flush()
    session.add(ExceptionRecord(id=uuid4().hex, case_id=case.id, exception_type=category,
        description="Current case still needs investigation", source_reference=uuid4().hex))
    session.commit()
    return case


def retrieve(session, settings, case, access=WORK_ACCESS, **kwargs):
    result = MemoryService(session, settings).retrieve(case.id, CATEGORY, access, **kwargs)
    session.commit()
    return result


@pytest.mark.parametrize("human", [False, True])
def test_verified_execution_creates_candidate_not_trusted_memory(session, settings, human):
    parts, request, record = candidate(session, settings, human)
    assert record["status"] == "CANDIDATE" and record["version"] == 1
    assert record["reviewer"] is None
    assert not retrieve(session, settings, new_case(session))["memories"]
    assert session.scalar(select(MemoryEvidence.evidence_id).where(MemoryEvidence.version_id == record["id"])) == request["evidence_ids"][0]
    assert session.scalar(select(AuditLog).where(AuditLog.entity_id == record["id"]))


@pytest.mark.parametrize("mutation", ["unresolved", "failed_verification", "wrong_verification_type", "execution_unverified", "action_unverified", "authorization_blocked", "authorization_tampered", "evidence_revoked", "wrong_case_evidence", "unknown_category"])
def test_invalid_source_cannot_create_memory(session, settings, mutation):
    parts, request = resolved(session, settings)
    verification = session.get(VerificationResult, request["verification_id"])
    evidence = session.get(Evidence, request["evidence_ids"][0])
    operation = session.scalar(select(ExecutionOperation).where(ExecutionOperation.case_id == parts[0].id))
    from app.controls.models import ControlAuthorization
    authorization = session.get(ControlAuthorization, operation.authorization_id)
    if mutation == "unresolved": parts[0].status = CaseState.ESCALATED
    if mutation == "failed_verification": verification.success = False
    if mutation == "wrong_verification_type": verification.verification_type = "AI_RECOMMENDATION"
    if mutation == "execution_unverified": operation.status = "VERIFYING"
    if mutation == "action_unverified": session.get(ActionRecord, verification.action_id).status = "VERIFYING"
    if mutation == "authorization_blocked": authorization.outcome = "BLOCKED"
    if mutation == "authorization_tampered": authorization.action = {**authorization.action, "payment_id": "another-payment"}
    if mutation == "evidence_revoked": evidence.integrity_metadata = {**evidence.integrity_metadata, "revoked": True}
    if mutation == "wrong_case_evidence": evidence.case_id = new_case(session).id
    if mutation == "unknown_category": request["category"] = "UNKNOWN"
    session.commit()
    with pytest.raises(ValueError):
        MemoryService(session, settings).candidate(parts[0].id, request, WORK_ACCESS)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(MemoryVersion)) == 0


def test_explicit_authorized_review_and_pending_state_required(session, settings):
    _, _, record = candidate(session, settings)
    with pytest.raises(PermissionError): transition(session, settings, record["id"], "SUBMIT", WORK_ACCESS)
    session.rollback()
    with pytest.raises(ValueError, match="transition_not_allowed"):
        transition(session, settings, record["id"], "APPROVE")
    session.rollback()
    transition(session, settings, record["id"], "SUBMIT")
    assert not retrieve(session, settings, new_case(session))["memories"]
    transition(session, settings, record["id"], "APPROVE")
    assert retrieve(session, settings, new_case(session))["memories"][0]["reviewer"] == REVIEWER.user_id


@pytest.mark.parametrize("operation", ["REJECT", "REVOKE", "WITHDRAW", "FLAG"])
def test_rejected_revoked_withdrawn_and_flagged_excluded(session, settings, operation):
    _, _, record = candidate(session, settings)
    transition(session, settings, record["id"], "SUBMIT")
    if operation != "REJECT": transition(session, settings, record["id"], "APPROVE")
    result = transition(session, settings, record["id"], operation)
    assert result["status"] == ("REJECTED" if operation == "REJECT" else "REVOKED")
    assert retrieve(session, settings, new_case(session))["memories"] == []


def test_correction_and_supersession_preserve_summary_and_audit_history(session, settings):
    _, _, record = publish(session, settings)
    current = new_case(session)
    corrected = transition(session, settings, record["id"], "CORRECT", summary="Corrected historical interpretation")
    replacement = corrected["replacement_id"]
    assert session.get(MemoryVersion, record["id"]).summary == record["summary"]
    assert retrieve(session, settings, current)["memories"][0]["id"] == record["id"]
    transition(session, settings, replacement, "SUBMIT")
    transition(session, settings, replacement, "APPROVE")
    result = retrieve(session, settings, current)
    assert [row["id"] for row in result["memories"]] == [replacement]
    assert result["memories"][0]["version"] == 2
    session.refresh(session.get(MemoryVersion, record["id"]))
    assert session.get(MemoryVersion, record["id"]).status == "SUPERSEDED"
    operations = session.scalars(select(MemoryReview.operation).where(MemoryReview.version_id == record["id"])).all()
    assert set(operations) == {"CREATE", "SUBMIT", "APPROVE", "CORRECT", "SUPERSEDE"}
    assert session.scalar(select(AuditLog).where(AuditLog.entity_id == record["id"], AuditLog.event_type == "memory_supersede"))


@pytest.mark.parametrize("mutation", ["evidence_revoked", "evidence_corrected", "event_corrected", "event_revoked", "outcome_corrected", "new_failed_outcome", "approval_withdrawn", "governance_changed", "verification_event_invalid", "source_category_corrected"])
def test_invalidation_fails_closed_and_reconciliation_audits_revocation(session, settings, mutation):
    parts, request, record = publish(session, settings, human=True)
    evidence = session.get(Evidence, request["evidence_ids"][0])
    event = session.get(EventRecord, evidence.integrity_metadata["event_record_id"])
    verification = session.get(VerificationResult, request["verification_id"])
    if mutation == "evidence_revoked": evidence.integrity_metadata = {**evidence.integrity_metadata, "revoked": True}
    if mutation == "evidence_corrected": evidence.payload = {"payment_status": "FAILED"}
    if mutation == "event_corrected": event.payload = {**event.payload, "payment_status": "FAILED"}
    if mutation == "event_revoked": event.processing_status = "REVOKED"
    if mutation == "outcome_corrected": verification.success = False
    if mutation == "new_failed_outcome":
        session.add(VerificationResult(id=uuid4().hex, case_id=parts[0].id, action_id=verification.action_id,
            verification_type=verification.verification_type, success=False, created_at=MemoryService(session).now()))
    if mutation == "approval_withdrawn":
        human = session.scalar(select(HumanApproval).where(HumanApproval.case_id == parts[0].id))
        human.approved = False
    if mutation == "governance_changed": session.get(MemoryVersion, record["id"]).governance_version = "retired-memory-policy"
    if mutation == "verification_event_invalid":
        confirmation = session.scalar(select(EventRecord).where(EventRecord.source_system == "confirmations",
            EventRecord.entity_reference == parts[3].payment_id))
        confirmation.processing_status = "REVOKED"
    if mutation == "source_category_corrected":
        session.scalar(select(ExceptionRecord).where(ExceptionRecord.case_id == parts[0].id)).exception_type = "CORRECTED_CATEGORY"
    session.commit()
    assert not retrieve(session, settings, new_case(session))["memories"]
    result = MemoryService(session, settings).reconcile(record["id"], REVIEW_ACCESS)
    session.commit()
    assert result["status"] == "REVOKED"
    assert session.scalar(select(MemoryReview).where(MemoryReview.version_id == record["id"], MemoryReview.operation == "INVALIDATE"))


@pytest.mark.parametrize("mutation", ["relevant_policy", "expired_policy", "unrelated_policy"])
def test_policy_changes_keep_facts_and_mark_only_relevant_guidance_outdated(session, settings, mutation):
    parts, _, _ = publish(session, settings)
    policy = parts[2]
    if mutation == "relevant_policy":
        policy.content = {**policy.content, "max_amount": "50"}
    if mutation == "expired_policy": policy.is_active = False
    if mutation == "unrelated_policy":
        session.add(Policy(id=uuid4().hex, name="unrelated-" + uuid4().hex, active_version="new"))
    session.commit()
    result = retrieve(session, settings, new_case(session))
    assert result["status"] == "AVAILABLE"
    assert result["memories"][0]["guidance_status"] == ("REQUIRES_CURRENT_CONTROLS" if mutation == "unrelated_policy" else "OUTDATED_REMEDIATION_GUIDANCE")
    assert result["action_authorization"] == "NOT_EVALUATED"


def test_case_user_source_and_production_access_boundaries(session, settings):
    parts, _, record = publish(session, settings)
    current = new_case(session)
    scoped = MemoryAccess(WORKER, frozenset({current.id}), frozenset({"payments"}))
    assert not retrieve(session, settings, current, scoped)["memories"]
    with pytest.raises(PermissionError): retrieve(session, settings, current, MemoryAccess(WORKER, frozenset({parts[0].id})))
    session.rollback()
    with pytest.raises(PermissionError): retrieve(session, settings, current, MemoryAccess(Identity("outsider", frozenset())))
    session.rollback()
    denied_source = MemoryAccess(WORKER, frozenset({current.id, parts[0].id}), frozenset({"ledger"}))
    assert not retrieve(session, settings, current, denied_source)["memories"]
    assert session.get(MemoryVersion, record["id"]).status == "ACTIVE"
    production = MemoryService(session, Settings(environment="production"))
    with pytest.raises(PermissionError, match="explicit_memory_access_required"):
        production.retrieve(current.id, CATEGORY, WORK_ACCESS)
    session.rollback()
    permitted = MemoryAccess(WORKER, frozenset({current.id, parts[0].id}), frozenset({"payments"}))
    assert production.retrieve(current.id, CATEGORY, permitted)["memories"]


def test_concurrent_reviewers_one_atomic_approval(session, settings, postgres_engine):
    _, _, record = candidate(session, settings)
    transition(session, settings, record["id"], "SUBMIT")
    barrier = Barrier(2)
    def approve(actor):
        with Session(postgres_engine) as other:
            barrier.wait(timeout=10)
            try:
                value = MemoryService(other, settings).review(record["id"],
                    dict(operation="APPROVE", reason="Concurrent independent reviewer"),
                    MemoryAccess(Identity(actor, frozenset({"OPERATIONS_REVIEWER"}))))
                other.commit()
                return value["status"]
            except ValueError:
                other.rollback()
                return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, ["reviewer-a", "reviewer-b"]))
    assert sorted(results) == ["ACTIVE", "CONFLICT"]
    assert session.scalar(select(func.count()).select_from(MemoryReview).where(MemoryReview.operation == "APPROVE")) == 1


def test_competing_corrected_versions_cannot_both_be_active(session, settings, postgres_engine):
    _, _, record = publish(session, settings)
    replacements = []
    for summary in ["Correction A", "Correction B"]:
        replacement = transition(session, settings, record["id"], "CORRECT", summary=summary)["replacement_id"]
        transition(session, settings, replacement, "SUBMIT")
        replacements.append(replacement)
    barrier = Barrier(2)
    def approve(version_id):
        with Session(postgres_engine) as other:
            barrier.wait(timeout=10)
            try:
                MemoryService(other, settings).review(version_id, dict(operation="APPROVE", reason="Review corrected facts"), REVIEW_ACCESS)
                other.commit()
                return "ACTIVE"
            except ValueError:
                other.rollback()
                return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, replacements)) == ["ACTIVE", "CONFLICT"]
    assert session.scalar(select(func.count()).select_from(MemoryVersion).where(MemoryVersion.status == "ACTIVE")) == 1


def test_review_transaction_rollback_preserves_pending_and_audit(session, settings):
    _, _, record = candidate(session, settings)
    transition(session, settings, record["id"], "SUBMIT")
    MemoryService(session, settings).review(record["id"], dict(operation="APPROVE", reason="Rollback before commit"), REVIEW_ACCESS)
    session.rollback()
    assert session.get(MemoryVersion, record["id"]).status == "PENDING_REVIEW"
    assert not session.scalar(select(MemoryReview).where(MemoryReview.operation == "APPROVE"))
    assert not session.scalar(select(AuditLog).where(AuditLog.event_type == "memory_approve"))


def test_corrected_source_requires_new_refs_and_fresh_review(session, settings):
    parts, request, record = publish(session, settings)
    old_evidence = session.get(Evidence, request["evidence_ids"][0])
    old_evidence.integrity_metadata = {**old_evidence.integrity_metadata, "revoked": True}
    replacement = Evidence(id=uuid4().hex, case_id=parts[0].id, source_system=old_evidence.source_system,
        source_record_id=old_evidence.source_record_id, relevant_event_timestamp=old_evidence.relevant_event_timestamp,
        payload=old_evidence.payload, integrity_metadata={key: value for key, value in old_evidence.integrity_metadata.items() if key != "revoked"})
    session.add(replacement)
    session.commit()
    corrected = transition(session, settings, record["id"], "CORRECT", summary="Corrected supporting reference",
        verification_id=request["verification_id"], evidence_ids=[replacement.id])
    corrected_id = corrected["replacement_id"]
    current = new_case(session)
    assert retrieve(session, settings, current)["memories"] == []
    transition(session, settings, corrected_id, "SUBMIT")
    transition(session, settings, corrected_id, "APPROVE")
    result = retrieve(session, settings, current)
    assert result["memories"][0]["evidence_references"][0]["evidence_id"] == replacement.id
    assert session.get(MemoryEvidence, (record["id"], old_evidence.id))


@pytest.mark.parametrize("submitted", [False, True])
def test_draft_corrections_withdraw_previous_summary_and_require_review(session, settings, submitted):
    _, _, record = candidate(session, settings)
    if submitted: transition(session, settings, record["id"], "SUBMIT")
    correction = transition(session, settings, record["id"], "CORRECT", summary="Corrected draft")
    replacement = correction["replacement_id"]
    assert correction["status"] == "REJECTED"
    assert session.get(MemoryVersion, replacement).status == "CANDIDATE"
    with pytest.raises(ValueError): transition(session, settings, record["id"], "APPROVE")
    session.rollback()
    transition(session, settings, replacement, "SUBMIT")
    transition(session, settings, replacement, "APPROVE")
    assert session.get(MemoryVersion, record["id"]).summary == record["summary"]


def test_publication_rechecks_evidence_after_candidate_submission(session, settings):
    _, request, record = candidate(session, settings)
    transition(session, settings, record["id"], "SUBMIT")
    evidence = session.get(Evidence, request["evidence_ids"][0])
    evidence.integrity_metadata = {**evidence.integrity_metadata, "revoked": True}
    session.commit()
    with pytest.raises(ValueError, match="memory_evidence_invalid"):
        transition(session, settings, record["id"], "APPROVE")
    session.rollback()
    assert session.get(MemoryVersion, record["id"]).status == "PENDING_REVIEW"
    assert not session.scalar(select(MemoryReview).where(MemoryReview.operation == "APPROVE"))


def test_retrieval_limits_determinism_and_audit(session, settings):
    for _ in range(3): publish(session, settings)
    current = new_case(session)
    first = retrieve(session, settings, current, top_k=2, context_bytes=8000)
    second = retrieve(session, settings, current, top_k=2, context_bytes=8000)
    assert first == second and len(first["memories"]) == 2 and first["truncated"]
    compact = retrieve(session, settings, current, top_k=2, context_bytes=512)
    assert len(json.dumps(compact, ensure_ascii=False).encode()) <= 512
    assert compact["truncated"] and not compact["memories"]
    for kwargs in [dict(top_k=0), dict(top_k=11), dict(context_bytes=16001)]:
        with pytest.raises(ValueError): retrieve(session, settings, current, **kwargs)
        session.rollback()
    assert session.scalar(select(func.count()).select_from(MemoryRetrieval)) == 3


def test_database_constraints_and_reviewed_content_integrity(session, settings):
    _, _, record = publish(session, settings)
    original = session.get(MemoryVersion, record["id"])
    duplicate = MemoryVersion(**{column.name: getattr(original, column.name) for column in MemoryVersion.__table__.columns
        if column.name not in {"id", "version"}}, id=uuid4().hex, version=2)
    session.add(duplicate)
    with pytest.raises(IntegrityError, match="uq_memory_active"):
        session.flush()
    session.rollback()
    original.summary = "Silent overwrite outside reviewed service"
    session.commit()
    assert not retrieve(session, settings, new_case(session))["memories"]


def test_memory_tool_cache_and_no_current_evidence_materialization(session, settings):
    _, _, record = publish(session, settings)
    current = new_case(session)
    calls = []
    def fetch(category):
        calls.append(category)
        return retrieve(session, settings, current)
    context = dict(scope=["READ_CASE_EVIDENCE"], events=[], exception_types=[CATEGORY])
    dispatcher = ToolDispatcher("RISK", context, fetch)
    result = dispatcher.dispatch("get_previous_verified_cases", {"exception_type": CATEGORY})
    assert result["label"] == LABEL and result["evidence"] == [] and dispatcher.used == set()
    assert dispatcher.dispatch("get_previous_verified_cases", {"exception_type": CATEGORY}) == result
    assert calls == [CATEGORY]
    historical_ref = result["memories"][0]["evidence_references"][0]["event_record_id"]
    with pytest.raises(EvidenceRejected): validate_output(output([historical_ref], "payment_status", "SETTLED"), context, dispatcher.used)
    with pytest.raises(ToolDenied): dispatcher.dispatch("get_previous_verified_cases", {"exception_type": "OTHER"})
    with pytest.raises(ToolDenied): ToolDispatcher("TRANSACTION", context, fetch).dispatch("get_previous_verified_cases", {"exception_type": CATEGORY})
    assert result["action_authorization"] == "NOT_EVALUATED"


class MemoryFirstModel(FakeModel):
    def __init__(self):
        super().__init__(role="RISK")
        self.memory_result = None

    def turn(self, instructions, messages, tools, max_tokens):
        if self.memory_result is None and self.calls == 0:
            self.calls = -1
            meta = json.loads(messages[0]["content"])
            return ModelTurn(calls=[ToolCall(name="get_previous_verified_cases",
                arguments={"exception_type": meta["exception_types"][0]}, call_id="memory")])
        if self.calls == -1:
            self.memory_result = json.loads(messages[-1]["output"])
            self.calls = 0
        return super().turn(instructions, messages, tools, max_tokens)


@pytest.mark.parametrize("failure", [False, True])
def test_memory_missing_or_failed_retrieval_preserves_investigator(session, settings, failure):
    provider = MemoryFirstModel()
    case, task, runner, claimed = prepare(session, settings, "RISK", provider)
    if failure:
        def unavailable(owner, context): raise ConnectionError("Memory adapter unavailable")
        runner.memory_access_provider = unavailable
    result = runner.run(task.id, "specialist", claimed["lease_token"])
    assert result["outcome"] == "COMPLETED"
    assert provider.memory_result["status"] == ("UNAVAILABLE" if failure else "MISSING")
    assert session.scalar(select(func.count()).select_from(ActionRecord).where(ActionRecord.case_id == case.id)) == 0


def test_successful_memory_investigation_still_queries_current_sources(session, settings):
    historical_parts, _, record = publish(session, settings)
    current_parts = fixture_case(session)
    case = current_parts[0]
    case.status = CaseState.INVESTIGATION_QUEUED
    workflow = OrchestrationService(session, settings)
    task = workflow.queue.schedule(workflow.payload(case, TaskType.INVESTIGATE_RISK,
        workflow.assessments([case.id])), "memory-investigation-" + uuid4().hex, priority=-100)
    workflow.queue.consumer(task, case.id, [item.id for item in workflow.assessments([case.id])])
    session.commit()
    class Provider(MemoryFirstModel):
        def turn(self, instructions, messages, tools, max_tokens):
            if self.calls < 1: return super().turn(instructions, messages, tools, max_tokens)
            self.calls += 1
            evidence = json.loads(messages[-1]["output"])["evidence"]
            refs = [row["id"] for row in evidence if "payment_status" in row["payload"]]
            return ModelTurn(output=output(refs, "payment_status", "SETTLED"))
    provider = Provider()
    database = DatabaseManager(session.get_bind().url)
    runner = InvestigationRunner(database, settings, provider)
    runner.activate(session)
    claimed = WorkQueue(session, settings, handlers=HANDLERS).claim("memory-specialist")[0]
    session.commit()
    assert claimed["id"] == task.id
    result = runner.run(task.id, "memory-specialist", claimed["lease_token"])
    assert result["outcome"] == "COMPLETED", result
    assert provider.memory_result["status"] == "AVAILABLE"
    assert provider.memory_result["memories"][0]["id"] == record["id"]
    assert result["evidence_references"] and all(row["evidence_id"] not in
        {item["evidence_id"] for item in provider.memory_result["memories"][0]["evidence_references"]}
        for row in result["evidence_references"])
    assert result["action_authorization"] == "NOT_EVALUATED"
    assert session.scalar(select(func.count()).select_from(ActionRecord).where(ActionRecord.case_id == case.id)) == 0


def test_protected_memory_api_uses_existing_identity_and_never_accepts_role_claims(session, settings, monkeypatch):
    from app.config import get_settings
    from app.main import create_app
    parts, request, record = candidate(session, settings)
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", "memory-test-worker-token-long-value")
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", "memory-test-reviewer-token-long-value")
    client = TestClient(create_app())
    try:
        url = "/api/v1/memory/versions/" + record["id"] + "/review"
        body = dict(operation="SUBMIT", reason="Explicit human review")
        assert client.post(url, json=body).status_code == 401
        assert client.post(url, json=body, headers={"Authorization": "Bearer memory-test-worker-token-long-value"}).status_code == 403
        reviewer = {"Authorization": "Bearer memory-test-reviewer-token-long-value"}
        assert client.post(url, json={**body, "roles": ["OPERATIONS_REVIEWER"]}, headers=reviewer).status_code == 422
        assert client.post(url, json=body, headers=reviewer).json()["status"] == "PENDING_REVIEW"
        assert client.post(url, json={**body, "operation": "APPROVE"}, headers=reviewer).json()["status"] == "ACTIVE"
        history = client.get(url.removesuffix("/review") + "/history", headers=reviewer)
        assert history.status_code == 200 and len(history.json()) == 3
        assert client.get(f"/api/v1/cases/{parts[0].id}/memory", headers=reviewer).status_code == 200
    finally:
        client.close()
