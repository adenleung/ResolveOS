import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.main import app
from app.simulator.models import SyntheticPayment
from app.simulator.service import SimulatorScenarioService
from tests.ground_truth import SCENARIO_GROUND_TRUTH


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        pytest.skip("PostgreSQL integration tests require DATABASE_URL to point to PostgreSQL")
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def simulator_session(postgres_engine):
    with Session(postgres_engine) as session:
        session.execute(text("DELETE FROM sim_technology_logs"))
        session.execute(text("DELETE FROM sim_confirmation_events"))
        session.execute(text("DELETE FROM sim_ledger_entries"))
        session.execute(text("DELETE FROM sim_workflow_states"))
        session.execute(text("DELETE FROM sim_payments"))
        session.execute(text("DELETE FROM sim_policies"))
        session.commit()
        yield session


def test_scenario_generation_creates_consistent_payment_and_ledger_records(simulator_session):
    service = SimulatorScenarioService(simulator_session)
    scenario = service.generate_scenario("normal_success", seed=99)

    payment = service.get_payment(scenario["payment_id"])
    assert payment is not None
    assert payment.status == "SETTLED"
    ledger_rows = service.get_ledger_records(scenario["payment_id"])
    assert len(ledger_rows) == 1
    assert ledger_rows[0].payment_id == payment.id
    assert service.get_logs(correlation_id=scenario["correlation_id"])  # ensures log output exists


def test_scenario_generation_is_reproducible(simulator_session):
    service = SimulatorScenarioService(simulator_session)
    first = service.generate_scenario("missing_confirmation", seed=77)
    second = service.generate_scenario("missing_confirmation", seed=77)
    assert first["payment_id"] == second["payment_id"]
    assert first["correlation_id"] == second["correlation_id"]
    assert first["status"] == second["status"]


def test_duplicate_event_constraint_is_enforced(simulator_session):
    service = SimulatorScenarioService(simulator_session)
    scenario = service.generate_scenario("duplicate_event", seed=123)
    payment = service.get_payment(scenario["payment_id"])

    with Session(simulator_session.bind) as session:
        from app.simulator.models import SyntheticConfirmationEvent

        first = session.execute(text("SELECT event_id FROM sim_confirmation_events WHERE payment_id = :payment_id LIMIT 1"), {"payment_id": payment.id}).scalar_one()
        duplicate = SyntheticConfirmationEvent(
            id=f"dup-{uuid.uuid4().hex}",
            payment_id=payment.id,
            event_id=first,
            event_type="payment_confirmed",
            status="REPLAYED",
            occurred_at=payment.created_at,
            correlation_id=scenario["correlation_id"],
            is_duplicate=True,
            payload={"duplicate": True},
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_foreign_key_and_idempotency_constraints_hold(simulator_session):
    service = SimulatorScenarioService(simulator_session)
    scenario = service.generate_scenario("duplicate_payment_risk", seed=456)
    payment = service.get_payment(scenario["payment_id"])

    with Session(simulator_session.bind) as session:
        from app.simulator.models import SyntheticLedgerEntry

        invalid = SyntheticLedgerEntry(
            id=f"invalid-ledger-{uuid.uuid4().hex}",
            payment_id="missing-id",
            ledger_transaction_id=f"missing-ledger-{uuid.uuid4().hex}",
            entry_type="DEBIT",
            amount=payment.amount,
            currency=payment.currency,
            balance_after=payment.amount,
            source_system="ledger",
            status="POSTED",
            description="invalid",
        )
        session.add(invalid)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_runtime_api_does_not_expose_ground_truth(simulator_session):
    with TestClient(app) as client:
        response = client.post("/api/v1/simulator/scenarios/generate", json={"scenario_name": "normal_success", "seed": 11})
        assert response.status_code == 200
        payload = response.json()
        assert "root_cause" not in payload
        assert payload["status"] == "SETTLED"


def test_reset_endpoint_is_allowed_in_development(simulator_session):
    with TestClient(app) as client:
        response = client.delete("/api/v1/simulator/reset")
        assert response.status_code == 200
        assert response.json()["status"] == "reset"


def test_phase2_ground_truth_mapping_matches_runtime_status(simulator_session):
    service = SimulatorScenarioService(simulator_session)
    for scenario_name, expected in SCENARIO_GROUND_TRUTH.items():
        generated = service.generate_scenario(scenario_name, seed=expected["expected_status"] and 10)
        assert generated["status"] == expected["expected_status"]


def test_phase2_transaction_rollback_does_not_persist_partial_scenario(simulator_session):
    with Session(simulator_session.bind) as outer_session:
        before = outer_session.execute(text("SELECT COUNT(*) FROM sim_payments")).scalar_one()
        with Session(simulator_session.bind) as session:
            try:
                with session.begin():
                    session.add(
                        SyntheticPayment(
                            id=f"rollback-{uuid.uuid4().hex}",
                            payment_id=f"rollback-payment-{uuid.uuid4().hex}",
                            idempotency_key=f"rollback-key-{uuid.uuid4().hex}",
                            amount=50,
                            currency="SGD",
                            beneficiary="rollback-beneficiary",
                            status="PENDING",
                            correlation_id=f"correlation-{uuid.uuid4().hex}",
                            incident_key=f"incident-{uuid.uuid4().hex}",
                            scenario_name="rollback_test",
                            processing_outcome="rollback",
                            expected_root_cause="rollback",
                        )
                    )
                    raise RuntimeError("forced rollback")
            except RuntimeError:
                pass
        after = outer_session.execute(text("SELECT COUNT(*) FROM sim_payments")).scalar_one()
        assert after == before
