from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import DatabaseManager
from app.main import app
from app.models.domain import Case


def test_application_startup_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_database_migration_creates_core_tables():
    database = DatabaseManager("sqlite:///:memory:")
    database.create_all()
    with database.engine.connect() as connection:
        result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='cases'"))
        assert result.scalar_one() == "cases"
        assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='event_records'")).scalar_one() == "event_records"
        assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='sim_payments'")).scalar_one() == "sim_payments"


def test_transaction_rollback_does_not_persist_partial_work():
    database = DatabaseManager("sqlite:///:memory:")
    database.create_all()
    with database.get_session() as session:
        session.add(
            Case(
                id="case-rollback",
                case_number="CASE-ROLLBACK-001",
                status="DETECTED",
                summary="Attempted rollback",
                priority="MEDIUM",
            )
        )
        session.commit()

        try:
            with session.begin():
                session.add(
                    Case(
                        id="case-rollback-2",
                        case_number="CASE-ROLLBACK-002",
                        status="DETECTED",
                        summary="Will fail",
                        priority="MEDIUM",
                    )
                )
                raise RuntimeError("forced rollback")
        except RuntimeError:
            pass

        assert session.query(Case).count() == 1
