from __future__ import annotations

import json
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.orm import Session

from app.classification.models import AssessmentHistory
from app.classification.service import ClassificationService
from app.config import Settings
from app.correlation.service import IncidentCorrelationService
from app.domain.case_service import CaseState
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import EventRecord
from app.ingestion.service import EventIngestionService
from app.main import create_app
from app.models.domain import ActionRecord, AuditLog, Case, CaseIncident, ExceptionRecord, HumanApproval, Incident
from app.orchestration.auth import Identity
from app.orchestration.contracts import InvestigationResult, TaskPayload, TaskType
from app.orchestration.models import ReviewHistory, TaskConsumer, TaskHistory, WorkflowReview, WorkTask
from app.orchestration.queue import LeaseLost, WorkQueue, utc
from app.orchestration.service import OrchestrationService


@pytest.fixture(scope="module")
def postgres_engine():
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("Phase 6 tests require PostgreSQL")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(postgres_engine):
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        for model in (ReviewHistory, WorkflowReview, TaskHistory, TaskConsumer, WorkTask):
            session.execute(delete(model))
        session.commit()
        yield session
        session.rollback()
        for model in (ReviewHistory, WorkflowReview, TaskHistory, TaskConsumer, WorkTask):
            session.execute(delete(model))
        session.commit()


@pytest.fixture
def settings():
    return Settings(orchestration_backoff_seconds=1, orchestration_lease_seconds=2,
        orchestration_fairness_seconds=30, orchestration_max_attempts=2)


def make_case(session, status=CaseState.DETECTED, priority="MEDIUM", deadline=None):
    case = Case(id="phase6-" + uuid4().hex, case_number="P6-" + uuid4().hex,
        status=status, priority=priority, sla_started_at=datetime.now(timezone.utc), sla_deadline=deadline)
    session.add(case)
    session.commit()
    return case


def source_case(session, incident_identifier=None):
    # Real normalized synthetic events, not a hardcoded scenario-name routing expectation.
    entity = "phase6-payment-" + uuid4().hex
    now = datetime.now(timezone.utc)
    source = {"event_id": "observed-" + uuid4().hex, "entity_reference": entity,
        "correlation_id": "trace-" + uuid4().hex, "schema_version": "1.0", "occurred_at": now}
    records = [dict(source, source_system="payments", event_type="payment.recorded", source_record_reference=entity,
        payload={"payment_status": "TIMEOUT", "amount": "500", "currency": "SGD", "idempotency_key": uuid4().hex}),
        dict(source, event_id=uuid4().hex, source_system="api_gateway", event_type="api.request_completed",
            source_record_reference="api-" + uuid4().hex, payload={"service_name": "payment-service", "endpoint": "/settle",
                "status_code": 504, "latency_ms": 45000, "error_type": "timeout", "incident_identifier": incident_identifier})]
    EventIngestionService(session).ingest(records)
    ExceptionDetectionService(session).run()
    exception = session.execute(select(ExceptionRecord).where(ExceptionRecord.source_reference == entity,
        ExceptionRecord.exception_type == "API_PROCESSING_FAILURE")).scalar_one()
    ClassificationService(session).evaluate(exception.id)
    return session.get(Case, exception.case_id), exception


def drain(session, settings, limit=20):
    executed = []
    for _ in range(limit):
        service = OrchestrationService(session, settings)
        claimed = service.queue.claim("test-worker")
        session.commit()
        if not claimed:
            break
        task = claimed[0]
        service.execute(task["id"], "test-worker", task["lease_token"])
        executed.append(task["task_type"])
    return executed


def task_for(session, settings, case=None, kind=TaskType.ROUTE_CASE, **kwargs):
    case = case or make_case(session)
    task = WorkQueue(session, settings).schedule(TaskPayload(case_id=case.id, task_type=kind),
        "test-" + uuid4().hex, **kwargs)
    session.commit()
    return task


def test_case_workflow_and_dynamic_specialists(session, settings):
    case, exception = source_case(session)
    service = OrchestrationService(session, settings)
    started = case.sla_started_at
    service.schedule_case(case.id)
    assert "CLASSIFY_CASE" in drain(session, settings)
    session.refresh(case)
    assert case.status == CaseState.INVESTIGATION_QUEUED
    tasks = session.execute(select(WorkTask).where(WorkTask.case_id == case.id,
        WorkTask.task_type.like("INVESTIGATE_%"))).scalars().all()
    assert {task.task_type for task in tasks} == {"INVESTIGATE_TRANSACTION", "INVESTIGATE_TECHNOLOGY"}
    assert all(task.status == "WAITING_HANDLER" and task.attempt_count == 0 for task in tasks)
    assert all(task.payload["assessment_ids"] and task.payload["evidence_references"] for task in tasks)
    assert case.sla_started_at == started


def test_invalid_and_future_execution_transitions_are_not_driven_by_orchestrator(session, settings):
    case = make_case(session)
    service = OrchestrationService(session, settings)
    with pytest.raises(ValueError):
        service.transition(case, CaseState.RESOLVED, "Invalid jump")
    case.status = CaseState.APPROVED
    session.commit()
    assert service.schedule_case(case.id)["scheduled"] == []
    assert case.status == CaseState.APPROVED
    assert session.query(ActionRecord).filter_by(case_id=case.id).count() == 0


def test_duplicate_scheduling_with_independent_sessions(session, settings, postgres_engine):
    case = make_case(session)
    def schedule(_):
        with Session(postgres_engine) as independent:
            return OrchestrationService(independent, settings).schedule_case(case.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(schedule, range(2)))
    assert results[0]["scheduled"] == results[1]["scheduled"]
    assert session.query(WorkTask).filter_by(case_id=case.id, task_type="CLASSIFY_CASE").count() == 1


def test_claim_exclusivity_across_independent_sessions(session, settings, postgres_engine):
    task_for(session, settings)
    def claim(owner):
        with Session(postgres_engine) as independent:
            result = WorkQueue(independent, settings).claim(owner)
            independent.commit()
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["one", "two"]))
    assert sum(len(items) for items in results) == 1


def test_skip_locked_does_not_wait_for_another_claim_transaction(session, settings, postgres_engine):
    first = task_for(session, settings)
    second = task_for(session, settings)
    with Session(postgres_engine) as locker:
        locker.execute(select(WorkTask).where(WorkTask.id == first.id).with_for_update()).scalar_one()
        claimed = WorkQueue(session, settings).claim("other")
        session.commit()
    assert [item["id"] for item in claimed] == [second.id]


def test_lease_expiry_recovery_and_stale_worker_fencing(session, settings, postgres_engine):
    task = task_for(session, settings)
    queue = WorkQueue(session, settings)
    lease = queue.claim("crashed")[0]
    session.commit()
    session.execute(text("UPDATE orchestration_tasks SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": task.id})
    session.commit()
    with Session(postgres_engine) as recovery:
        assert WorkQueue(recovery, settings).recover() == 1
        recovery.commit()
    with pytest.raises(LeaseLost):
        queue.complete(task.id, "crashed", lease["lease_token"], {"fake": True})
    session.rollback()
    session.execute(text("UPDATE orchestration_tasks SET scheduled_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": task.id})
    session.commit()
    next_lease = queue.claim("restarted")[0]
    session.commit()
    assert next_lease["lease_token"] != lease["lease_token"]
    with pytest.raises(LeaseLost):
        queue.renew(task.id, "crashed", lease["lease_token"])
    session.rollback()
    queue.complete(task.id, "restarted", next_lease["lease_token"], {"recovered": True})
    session.commit()


def test_renewal_and_expired_lease_cannot_renew(session, settings):
    task = task_for(session, settings)
    queue = WorkQueue(session, settings)
    claim = queue.claim("worker")[0]
    session.commit()
    renewed = queue.renew(task.id, "worker", claim["lease_token"])
    session.commit()
    assert renewed["lease_token"] == claim["lease_token"]
    session.execute(text("UPDATE orchestration_tasks SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": task.id})
    session.commit()
    with pytest.raises(LeaseLost):
        queue.renew(task.id, "worker", claim["lease_token"])
    session.rollback()


def test_retry_exhaustion_dead_letter_and_explicit_requeue(session, settings):
    task = task_for(session, settings)
    queue = WorkQueue(session, settings)
    for attempt in range(2):
        claim = queue.claim("worker")[0]
        session.commit()
        failed = queue.fail(task.id, "worker", claim["lease_token"], "TRANSIENT_DATABASE", transient=True)
        session.commit()
        assert failed["status"] == ("RETRY_WAIT" if attempt == 0 else "DEAD_LETTER")
        session.execute(text("UPDATE orchestration_tasks SET scheduled_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": task.id})
        session.commit()
    with pytest.raises(ValueError):
        queue.requeue(task.id, "No added budget", 2)
    session.rollback()
    result = queue.requeue(task.id, "Operator investigated transient failure", 3)
    session.commit()
    assert result["attempt_count"] == 2 and result["status"] == "PENDING"
    assert session.query(WorkTask).count() == 1


def test_permanent_invalid_payload_rolls_back_partial_handler_effects(session, settings):
    case = make_case(session)
    task = task_for(session, settings, case, TaskType.CLASSIFY_CASE)
    task.payload = {**task.payload, "task_version": "unsupported"}
    session.commit()
    queue = WorkQueue(session, settings)
    claim = queue.claim("worker")[0]
    session.commit()
    with pytest.raises(ValidationError):
        OrchestrationService(session, settings).execute(task.id, "worker", claim["lease_token"])
    session.rollback()
    queue.fail(task.id, "worker", claim["lease_token"], "INVALID_TASK_VERSION", transient=False)
    session.commit()
    session.refresh(task)
    assert task.status == "DEAD_LETTER"
    assert session.query(AssessmentHistory).filter_by(case_id=case.id).count() == 0


def test_handler_results_rollback_when_lease_expires_during_work(session, settings):
    case, exception = source_case(session)
    service = OrchestrationService(session, settings)
    service.schedule_case(case.id)
    claim = service.queue.claim("worker")[0]
    session.commit()
    now = datetime.now(timezone.utc)
    calls = [0]
    def clock():
        calls[0] += 1
        return now if calls[0] < 3 else now + timedelta(hours=1)
    failing = OrchestrationService(session, settings, clock=clock)
    with pytest.raises(LeaseLost):
        failing.execute(claim["id"], "worker", claim["lease_token"])
    session.rollback()
    assert session.query(WorkTask).filter_by(case_id=case.id, task_type="ROUTE_CASE").count() == 0
    assert session.query(WorkTask).filter_by(id=claim["id"], status="RUNNING").count() == 1


def test_fair_scheduling_prioritizes_aged_low_priority_work(session, settings):
    low = task_for(session, settings, priority=3)
    high = task_for(session, settings, priority=0)
    session.execute(text("UPDATE orchestration_tasks SET created_at=clock_timestamp()-interval '60 seconds' WHERE id=:id"), {"id": low.id})
    session.commit()
    assert WorkQueue(session, settings).claim("fair")[0]["id"] == low.id
    session.commit()


def test_priority_order_within_fresh_work(session, settings):
    low = task_for(session, settings, priority=3)
    urgent = task_for(session, settings, priority=0)
    assert WorkQueue(session, settings).claim("urgent")[0]["id"] == urgent.id
    session.commit()


def test_sla_breach_and_review_expiry_do_not_reset_sla(session, settings):
    case = make_case(session, CaseState.TRIAGED, deadline=datetime.now(timezone.utc) - timedelta(seconds=1))
    start = case.sla_started_at
    service = OrchestrationService(session, settings)
    service.check_sla(case)
    service.check_sla(case)
    session.commit()
    assert session.query(WorkflowReview).filter_by(case_id=case.id).count() == 1
    assert session.query(AuditLog).filter_by(case_id=case.id, event_type="orchestration_sla_breached").count() == 1
    review = session.query(WorkflowReview).filter_by(case_id=case.id).one()
    review.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    service.maintenance()
    session.refresh(case)
    session.refresh(review)
    assert case.status == CaseState.ESCALATED and review.status == "EXPIRED"
    assert case.sla_started_at == start


def test_unavailable_future_handler_is_never_claimed_or_completed(session, settings):
    for kind in (TaskType.INVESTIGATE_TRANSACTION, TaskType.REQUEST_SUPERVISOR_REVIEW,
                 TaskType.PREPARE_EXECUTION, TaskType.REQUEST_VERIFICATION):
        task = task_for(session, settings, kind=kind)
        assert task.status == "WAITING_HANDLER"
    assert WorkQueue(session, settings).claim("phase6-worker", 100) == []
    assert session.query(WorkTask).filter_by(status="COMPLETED").count() == 0


def test_investigation_deadline_becomes_explicit_failure_and_review(session, settings):
    case = make_case(session, CaseState.INVESTIGATION_QUEUED)
    task = task_for(session, settings, case, TaskType.INVESTIGATE_RISK)
    WorkQueue(session, settings).consumer(task, case.id, [])
    task.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    OrchestrationService(session, settings).maintenance()
    session.refresh(task)
    session.refresh(case)
    assert task.status == "DEAD_LETTER" and task.last_error == "task_deadline_expired"
    assert case.status == CaseState.AWAITING_HUMAN


def create_review(session, settings):
    case = make_case(session)
    service = OrchestrationService(session, settings)
    service.schedule_case(case.id)
    drain(session, settings)
    return case, session.query(WorkflowReview).filter_by(case_id=case.id, status="OPEN").one()


def test_human_permissions_and_workflow_approval_is_not_authorization(session, settings):
    case, review = create_review(session, settings)
    service = OrchestrationService(session, settings)
    with pytest.raises(PermissionError):
        service.decide_review(review.id, Identity("intruder", frozenset({"WORKER"})), "APPROVE", "Spoofed role")
    session.rollback()
    reviewer = Identity("reviewer", frozenset({"OPERATIONS_REVIEWER"}))
    result = service.decide_review(review.id, reviewer, "APPROVE", "Workflow assessed")
    assert result["action_authorization"] == "NOT_EVALUATED"
    assert result["case_status"] == "APPROVED"
    assert session.query(WorkTask).filter_by(case_id=case.id, task_type="PREPARE_EXECUTION", status="WAITING_HANDLER").count() == 1
    assert session.query(ActionRecord).filter_by(case_id=case.id).count() == 0
    assert session.query(HumanApproval).filter_by(case_id=case.id).count() == 0


@pytest.mark.parametrize("decision,expected", [("REJECT", CaseState.BLOCKED), ("REQUEST_MORE_INVESTIGATION", CaseState.INVESTIGATION_QUEUED)])
def test_human_reject_and_more_investigation(session, settings, decision, expected):
    case, review = create_review(session, settings)
    result = OrchestrationService(session, settings).decide_review(review.id,
        Identity("reviewer", frozenset({"OPERATIONS_REVIEWER"})), decision, "Operational review")
    assert result["case_status"] == expected.value
    assert session.query(ReviewHistory).filter_by(review_id=review.id).count() == 2


def test_assigned_reviewer_and_closed_review_are_enforced(session, settings):
    case, review = create_review(session, settings)
    review.assigned_reviewer = "named-reviewer"
    session.commit()
    service = OrchestrationService(session, settings)
    with pytest.raises(PermissionError):
        service.decide_review(review.id, Identity("other", frozenset({"OPERATIONS_REVIEWER"})), "APPROVE", "Wrong assignee")
    session.rollback()
    identity = Identity("named-reviewer", frozenset({"OPERATIONS_REVIEWER"}))
    service.decide_review(review.id, identity, "REJECT", "Reviewed")
    with pytest.raises(ValueError):
        service.decide_review(review.id, identity, "APPROVE", "Cannot reverse closed review")
    session.rollback()


def test_material_evidence_change_reroutes_and_preserves_old_work(session, settings):
    case, exception = source_case(session)
    service = OrchestrationService(session, settings)
    service.schedule_case(case.id)
    drain(session, settings)
    original = session.query(WorkTask).filter_by(case_id=case.id, task_type="INVESTIGATE_TECHNOLOGY").one()
    observed = session.query(EventRecord).filter_by(entity_reference=exception.source_reference, source_system="api_gateway").one()
    EventIngestionService(session).ingest([dict(event_id=uuid4().hex, source_system=observed.source_system,
        event_type=observed.event_type, entity_reference=observed.entity_reference, correlation_id=observed.correlation_id,
        occurred_at=datetime.now(timezone.utc), source_record_reference=observed.source_record_reference, schema_version="1.0",
        payload={**observed.payload, "status_code": 200, "latency_ms": 100, "error_type": None})])
    service.schedule_case(case.id, reevaluate=True)
    drain(session, settings)
    session.refresh(original)
    session.refresh(case)
    assert original.status == "CANCELLED"
    assert case.status == CaseState.AWAITING_HUMAN
    assert session.query(WorkflowReview).filter_by(case_id=case.id, status="OPEN").count() == 1


def test_shared_incident_work_uses_one_technology_task_and_individual_transaction_tasks(session, settings):
    identifier = "observed-incident-" + uuid4().hex
    pairs = [source_case(session, identifier) for _ in range(2)]
    cases = [pair[0] for pair in pairs]
    IncidentCorrelationService(session).run(case_ids=[case.id for case in cases])
    service = OrchestrationService(session, settings)
    for case in cases:
        service.schedule_case(case.id)
    drain(session, settings)
    tasks = session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").all()
    assert len(tasks) == 1 and tasks[0].incident_id
    assert session.query(TaskConsumer).filter_by(task_id=tasks[0].id, active=True).count() == 2
    assert session.query(WorkTask).filter_by(task_type="INVESTIGATE_TRANSACTION", status="WAITING_HANDLER").count() == 2
    for case in cases:
        session.refresh(case)
        assert case.status == CaseState.INVESTIGATION_QUEUED


def test_split_changes_incident_work_without_changing_case_authorization(session, settings):
    identifier = "observed-split-" + uuid4().hex
    cases = [source_case(session, identifier)[0] for _ in range(4)]
    ids = [case.id for case in cases]
    correlation = IncidentCorrelationService(session)
    correlation.run(case_ids=ids)
    parent = session.execute(select(Incident).join(CaseIncident).where(CaseIncident.case_id == ids[0], CaseIncident.removed_at.is_(None))).scalar_one()
    service = OrchestrationService(session, settings)
    for case_id in ids:
        service.schedule_case(case_id)
    drain(session, settings)
    old = session.query(WorkTask).filter_by(incident_id=parent.id, task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").one()
    split = correlation.split_incident(parent.id, [ids[:2], ids[2:]], "Separate observed dependencies")
    for case_id in ids:
        service.schedule_case(case_id, reevaluate=True)
    drain(session, settings)
    session.refresh(old)
    assert old.status == "CANCELLED"
    active = session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").all()
    assert {task.incident_id for task in active} == set(split["child_incident_ids"])


def test_task_audit_completeness_and_restart_durability(session, settings, postgres_engine):
    case = make_case(session)
    task = task_for(session, settings, case)
    queue = WorkQueue(session, settings)
    claimed = queue.claim("worker")[0]
    session.commit()
    queue.renew(task.id, "worker", claimed["lease_token"])
    session.commit()
    queue.fail(task.id, "worker", claimed["lease_token"], "TEMPORARY", True)
    session.commit()
    with Session(postgres_engine) as restarted:
        stored = restarted.get(WorkTask, task.id)
        assert stored.status == "RETRY_WAIT" and stored.attempt_count == 1
    operations = {item.event_type for item in session.query(TaskHistory).filter_by(task_id=task.id)}
    assert operations == {"task_created", "task_claimed", "task_lease_renewed", "task_retry_scheduled"}
    audits = {item.event_type for item in session.query(AuditLog).filter_by(entity_id=task.id)}
    assert operations <= audits


def test_api_roles_default_off_and_production_denial(session, settings, monkeypatch):
    worker_token, reviewer_token = uuid4().hex, uuid4().hex
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", worker_token)
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", reviewer_token)
    monkeypatch.setenv("APP_ENV", "test")
    case, review = create_review(session, settings)
    with TestClient(create_app()) as client:
        assert client.get("/orchestration/stats").status_code == 404
        assert client.get("/api/v1/orchestration/stats").status_code == 401
        assert client.post("/api/v1/orchestration/worker/claim", json={"owner": "worker"},
            headers={"Authorization": "Bearer " + reviewer_token}).status_code == 403
        assert client.post(f"/api/v1/reviews/{review.id}/decision", json={"decision": "APPROVE", "reason": "Fake"},
            headers={"Authorization": "Bearer " + worker_token}).status_code == 403
        body = client.get(f"/api/v1/cases/{case.id}/tasks", headers={"Authorization": "Bearer " + reviewer_token}).json()
        assert "lease_token" not in json.dumps(body) and "root_cause" not in json.dumps(body)
        assert client.get("/api/v1/reviews", headers={"Authorization": "Bearer " + reviewer_token}).status_code == 200
        approved = client.post(f"/api/v1/reviews/{review.id}/decision", json={"decision": "APPROVE", "reason": "Workflow reviewed"},
            headers={"Authorization": "Bearer " + reviewer_token})
        assert approved.status_code == 200 and approved.json()["action_authorization"] == "NOT_EVALUATED"
    monkeypatch.setenv("APP_ENV", "production")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/orchestration/stats", headers={"Authorization": "Bearer " + worker_token}).status_code == 503
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "false")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/orchestration/stats").status_code == 503


def process_claim(url, owner, out):
    engine = create_engine(url)
    with Session(engine) as independent:
        claimed = WorkQueue(independent).claim(owner)
        independent.commit()
        out.put([item["id"] for item in claimed])
    engine.dispose()


def test_separate_worker_processes_claim_once(session, settings, postgres_engine):
    task = task_for(session, settings)
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    url = postgres_engine.url.render_as_string(hide_password=False)
    processes = [context.Process(target=process_claim, args=(url, f"process-{index}", results)) for index in range(2)]
    for process in processes:
        process.start()
    claims = [results.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert sum(len(items) for items in claims) == 1
    assert task.id in [task_id for items in claims for task_id in items]
    results.close()


def test_bounded_synthetic_queue_workload_and_query_plan(session, settings, postgres_engine):
    cases = [Case(id="phase6-load-" + uuid4().hex, case_number="LOAD-" + uuid4().hex,
                  status=CaseState.DETECTED, priority="MEDIUM") for _ in range(250)]
    session.add_all(cases)
    session.commit()
    queue = WorkQueue(session, settings)
    for case in cases:
        queue.schedule(TaskPayload(case_id=case.id, task_type=TaskType.REEVALUATE_CASE), "workload-" + uuid4().hex)
    session.commit()
    started = time.perf_counter()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))
    event.listen(postgres_engine, "before_cursor_execute", capture)
    try:
        claimed = queue.claim("workload", limit=20)
        session.commit()
    finally:
        event.remove(postgres_engine, "before_cursor_execute", capture)
    elapsed = time.perf_counter() - started
    assert len(claimed) == 20
    statement, parameters = next((statement, parameters) for statement, parameters in statements
        if "FROM orchestration_tasks" in statement and "ORDER BY orchestration_tasks.priority" in statement)
    plan = session.connection().exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters).scalar_one()
    stats = OrchestrationService(session, settings).stats()
    assert stats["tasks_by_status"]["RUNNING"] == 20
    measurements = {"queue_cases": 250, "queue_tasks": 250, "claimed": 20, "claim_seconds": round(elapsed, 4),
        "claim_sql_statements": len(statements), "poll_plan": plan[0]}
    Path("phase6-workload-results.json").write_text(json.dumps(measurements, indent=2), encoding="utf-8")
    print(measurements)


def test_confirmed_incident_merge_replaces_shared_work(session, settings):
    pairs = [source_case(session) for _ in range(4)]
    identifiers = ["upstream-a-" + uuid4().hex, "upstream-b-" + uuid4().hex]
    shared_trace = "shared-upstream-" + uuid4().hex
    for index, (case, exception) in enumerate(pairs):
        observed = session.query(EventRecord).filter_by(entity_reference=exception.source_reference, source_system="api_gateway").one()
        EventIngestionService(session).ingest([dict(event_id=uuid4().hex, source_system="api_gateway",
            event_type=observed.event_type, entity_reference=observed.entity_reference, correlation_id=shared_trace,
            occurred_at=datetime.now(timezone.utc), source_record_reference=observed.source_record_reference,
            schema_version="1.0", payload={**observed.payload, "incident_identifier": identifiers[index // 2]})])
        ClassificationService(session).evaluate(exception.id)
    ids = [pair[0].id for pair in pairs]
    correlation = IncidentCorrelationService(session)
    correlation.run(case_ids=ids)
    incident_ids = session.execute(select(CaseIncident.incident_id).where(CaseIncident.case_id.in_(ids),
        CaseIncident.removed_at.is_(None)).distinct()).scalars().all()
    assert len(incident_ids) == 2
    for incident_id in incident_ids:
        refs = [item["event_record_id"] for item in correlation.incident_summary(incident_id)["evidence_references"]]
        correlation.transition_status(incident_id, "INVESTIGATING", "Validate observed shared incident identifiers")
        correlation.transition_status(incident_id, "CONFIRMED", "Source evidence reviewed", refs)
    service = OrchestrationService(session, settings)
    for case_id in ids:
        service.schedule_case(case_id)
    drain(session, settings)
    assert session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").count() == 2
    refs = [item["event_record_id"] for incident_id in incident_ids for item in correlation.incident_summary(incident_id)["evidence_references"]]
    correlation.merge_incidents(incident_ids[0], incident_ids[1], "Reviewed common upstream trace across incidents", refs)
    for case_id in ids:
        service.schedule_case(case_id, reevaluate=True)
    drain(session, settings)
    active = session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").all()
    assert len(active) == 1 and active[0].incident_id == incident_ids[0]
    assert session.query(TaskConsumer).filter_by(task_id=active[0].id, active=True).count() == 4
    assert all(session.get(Case, case_id).status == CaseState.INVESTIGATION_QUEUED for case_id in ids)


def test_review_assignment_and_stale_assessment(session, settings):
    case, review = create_review(session, settings)
    service = OrchestrationService(session, settings)
    identity = Identity("assigned-reviewer", frozenset({"OPERATIONS_REVIEWER"}))
    service.assign_review(review.id, identity)
    assert session.query(ReviewHistory).filter_by(review_id=review.id, operation="ASSIGNED").count() == 1
    service.assign_review(review.id, identity)
    assert session.query(ReviewHistory).filter_by(review_id=review.id, operation="ASSIGNED").count() == 1
    with pytest.raises(PermissionError):
        service.assign_review(review.id, Identity("other", frozenset({"OPERATIONS_REVIEWER"})))
    session.rollback()
    # A changed assessment cannot be approved through a stale review snapshot.
    exception = ExceptionRecord(id=str(uuid4()), case_id=case.id, exception_type="UNSUPPORTED", description="Observed unknown condition")
    session.add(exception)
    session.commit()
    ClassificationService(session).evaluate(exception.id)
    with pytest.raises(ValueError, match="stale"):
        service.decide_review(review.id, identity, "APPROVE", "Assessment changed after review request")
    session.rollback()


def test_rolled_back_claim_is_available_after_worker_crash(session, settings, postgres_engine):
    task = task_for(session, settings)
    with Session(postgres_engine) as interrupted:
        claimed = WorkQueue(interrupted, settings).claim("interrupted-before-commit")
        assert claimed[0]["id"] == task.id
        interrupted.rollback()
    claimed = WorkQueue(session, settings).claim("replacement")
    session.commit()
    assert claimed[0]["id"] == task.id and claimed[0]["attempt_count"] == 1


def test_repeated_orchestration_does_not_duplicate_investigators(session, settings):
    case, exception = source_case(session)
    service = OrchestrationService(session, settings)
    for _ in range(3):
        service.schedule_case(case.id, reevaluate=True)
        drain(session, settings)
    assert session.query(WorkTask).filter_by(case_id=case.id, task_type="INVESTIGATE_TECHNOLOGY").count() == 1
    assert session.query(WorkTask).filter_by(case_id=case.id, task_type="INVESTIGATE_TRANSACTION").count() == 1


def test_incident_member_reclassification_invalidates_obsolete_shared_task(session, settings):
    identifier = "shared-refresh-" + uuid4().hex
    pairs = [source_case(session, identifier) for _ in range(2)]
    ids = [pair[0].id for pair in pairs]
    IncidentCorrelationService(session).run(case_ids=ids)
    service = OrchestrationService(session, settings)
    for case_id in ids:
        service.schedule_case(case_id)
    drain(session, settings)
    old = session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").one()
    changed = pairs[0][1]
    observed = session.query(EventRecord).filter_by(entity_reference=changed.source_reference, source_system="api_gateway").one()
    EventIngestionService(session).ingest([dict(event_id=uuid4().hex, source_system="api_gateway", event_type=observed.event_type,
        entity_reference=observed.entity_reference, correlation_id=observed.correlation_id, occurred_at=datetime.now(timezone.utc),
        source_record_reference=observed.source_record_reference, schema_version="1.0",
        payload={**observed.payload, "latency_ms": 60000})])
    service.schedule_case(ids[0], reevaluate=True)
    drain(session, settings)
    session.refresh(old)
    assert old.status == "CANCELLED"
    assert session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").count() == 1
    service.schedule_case(ids[1], reevaluate=True)
    drain(session, settings)
    active = session.query(WorkTask).filter_by(task_type="INVESTIGATE_TECHNOLOGY", status="WAITING_HANDLER").one()
    assert session.query(TaskConsumer).filter_by(task_id=active.id, active=True).count() == 2


def test_worker_cli_handles_permanent_error_and_keeps_claims_durable(session, settings, postgres_engine):
    from app.database import DatabaseManager
    from app.orchestration.worker import run_once
    case = make_case(session)
    task = task_for(session, settings, case, TaskType.CLASSIFY_CASE)
    task.payload = {**task.payload, "task_version": "invalid"}
    session.commit()
    database = DatabaseManager(postgres_engine.url.render_as_string(hide_password=False))
    try:
        result = run_once(database, "real-cli-worker", settings)
        assert result["claimed"] == 1
    finally:
        database.engine.dispose()
    session.refresh(task)
    assert task.status == "DEAD_LETTER" and task.last_error == "ValidationError"


def test_bounded_poll_discovers_all_cases_with_a_cursor(session, settings):
    for _ in range(5):
        make_case(session)
    configured = settings.model_copy(update={"orchestration_poll_limit": 2})
    service = OrchestrationService(session, configured)
    seen = []
    cursor = None
    for _ in range(1000):
        page = service.poll_cases(cursor)
        assert len(page["case_ids"]) <= 2
        seen.extend(page["case_ids"])
        cursor = page["next_after_case_id"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen))
    eligible = session.execute(select(Case.id).where(Case.status.in_([CaseState.DETECTED, CaseState.TRIAGED,
        CaseState.INVESTIGATION_QUEUED, CaseState.INVESTIGATING, CaseState.AWAITING_DECISION, CaseState.AWAITING_HUMAN]))).scalars().all()
    assert set(seen) == set(eligible)


def test_unclassified_new_evidence_cannot_receive_stale_workflow_approval(session, settings):
    case, review = create_review(session, settings)
    entity = "new-evidence-" + uuid4().hex
    exception = ExceptionRecord(id=str(uuid4()), case_id=case.id, exception_type="UNSUPPORTED", description="Observed issue",
        source_reference=entity)
    session.add(exception)
    session.commit()
    EventIngestionService(session).ingest([dict(event_id=uuid4().hex, source_system="documents", event_type="document.updated",
        entity_reference=entity, occurred_at=datetime.now(timezone.utc), schema_version="1.0",
        source_record_reference=entity, payload={"document_status": "MISSING"})])
    with pytest.raises(ValueError, match="evidence_or_incident_context_is_stale"):
        OrchestrationService(session, settings).decide_review(review.id,
            Identity("reviewer", frozenset({"OPERATIONS_REVIEWER"})), "APPROVE", "Stale review must not approve new facts")
    session.rollback()


def test_phase7_result_contract_has_no_action_authorization():
    result = InvestigationResult(task_id="task", lease_token="fence", assessment_ids=["assessment"], attempt_number=1,
        outcome="NEEDS_ADDITIONAL_EVIDENCE", summary="More observed evidence required")
    assert result.action_authorization == "NOT_EVALUATED"
    with pytest.raises(ValidationError):
        InvestigationResult(**{**result.model_dump(), "action_authorization": "AUTHORIZED"})
