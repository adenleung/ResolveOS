import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.case_service import CaseLifecycleService, CaseState
from app.models.domain import AuditLog, Case, Evidence


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        pytest.skip("PostgreSQL integration tests require DATABASE_URL to point to PostgreSQL")
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


def test_case_state_transition_is_valid_in_postgres_context():
    service = CaseLifecycleService()
    assert service.transition(CaseState.DETECTED, CaseState.TRIAGED) == CaseState.TRIAGED


def test_postgres_schema_contains_expected_tables(postgres_engine):
    with Session(postgres_engine) as session:
        rows = session.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name IN ('cases', 'exceptions', 'incidents', 'evidence', 'audit_logs') "
                "ORDER BY table_name"
            )
        ).scalars().all()
    assert rows == ["audit_logs", "cases", "evidence", "exceptions", "incidents"]


def test_postgres_unique_and_foreign_key_constraints_hold(postgres_engine):
    with Session(postgres_engine) as session:
        unique_case_number = f"PG-CASE-UNIQUE-{uuid.uuid4().hex[:8]}"
        case = Case(id=f"pg-case-{uuid.uuid4().hex}", case_number=unique_case_number, status=CaseState.DETECTED, summary="case", priority="MEDIUM")
        session.add(case)
        session.commit()

        duplicate = Case(id=f"pg-case-{uuid.uuid4().hex}", case_number=unique_case_number, status=CaseState.DETECTED, summary="duplicate", priority="MEDIUM")
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        invalid_evidence = Evidence(
            id=f"evidence-foreign-key-{uuid.uuid4().hex}",
            case_id="does-not-exist",
            source_system="ledger",
            source_record_id="txn-123",
            payload={"status": "missing"},
        )
        session.add(invalid_evidence)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_postgres_transaction_rollback_reverts_partial_work(postgres_engine):
    with Session(postgres_engine) as outer_session:
        initial_count = outer_session.execute(text("SELECT COUNT(*) FROM cases")).scalar_one()
        rollback_case_id = f"pg-case-rollback-{uuid.uuid4().hex}"

        with Session(postgres_engine) as session:
            try:
                with session.begin():
                    session.add(
                        Case(
                            id=rollback_case_id,
                            case_number=f"PG-ROLLBACK-{uuid.uuid4().hex[:8]}",
                            status=CaseState.DETECTED,
                            summary="rollback test",
                            priority="MEDIUM",
                        )
                    )
                    raise RuntimeError("forced rollback")
            except RuntimeError:
                pass

        final_count = outer_session.execute(text("SELECT COUNT(*) FROM cases")).scalar_one()
        assert final_count == initial_count


def test_postgres_audit_event_commits_with_related_case(postgres_engine):
    with Session(postgres_engine) as session:
        case_id = f"pg-case-audit-{uuid.uuid4().hex}"
        session.add(
            Case(
                id=case_id,
                case_number=f"PG-AUDIT-{uuid.uuid4().hex[:8]}",
                status=CaseState.DETECTED,
                summary="audit test",
                priority="MEDIUM",
            )
        )
        audit_id = f"audit-{uuid.uuid4().hex}"
        session.add(
            AuditLog(
                id=audit_id,
                case_id=case_id,
                entity_type="case",
                entity_id=case_id,
                event_type="case_created",
                summary="case created",
                details={"source": "integration_test"},
            )
        )
        session.commit()

        stored = session.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE case_id = :case_id AND entity_type = 'case'"),
            {"case_id": case_id},
        ).scalar_one()
        assert stored == 1
