import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_phase6_postgres import postgres_engine, source_case
from test_phase11_postgres import session, settings
from test_phase9_postgres import fixture_case, evaluate
from app.database import DatabaseManager
from app.demo import build_journeys, verify_journeys
from app.main import create_app
from app.models.domain import ActionRecord


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", session.get_bind().url.render_as_string(hide_password=False))
    monkeypatch.setenv("ORCHESTRATION_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_DEV_WORKER_TOKEN", "w" * 32)
    monkeypatch.setenv("ORCHESTRATION_DEV_REVIEWER_TOKEN", "r" * 32)
    with TestClient(create_app()) as result:
        yield result


WORKER = {"Authorization": "Bearer " + "w" * 32}
REVIEWER = {"Authorization": "Bearer " + "r" * 32}


def test_actual_three_journeys(session, settings, client):
    manifest = build_journeys(DatabaseManager(session.get_bind().url), settings)
    verify_journeys(DatabaseManager(session.get_bind().url), manifest)
    assert manifest["verified_assertions"]["duplicate_execution_single_effect"]
    for journey in manifest["journeys"].values():
        result = client.get("/api/v1/workbench/cases/" + journey["case_id"], headers=REVIEWER)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["case"]["id"] == journey["case_id"] and body["evidence"] and body["assessments"]
    assert client.get("/api/v1/workbench/memories", headers=REVIEWER).json()["items"][0]["currently_valid_historical_memory"]


def test_case_search_pagination_and_source_filtering(session, client):
    case, _ = source_case(session)
    assert client.get("/api/v1/workbench/cases").status_code == 401
    page = client.get("/api/v1/workbench/cases", params={"q": case.case_number, "limit": 1}, headers=REVIEWER).json()
    assert page["total"] == 1 and page["items"][0]["id"] == case.id
    detail = client.get("/api/v1/workbench/cases/" + case.id, headers=REVIEWER)
    assert detail.status_code == 200 and detail.json()["evidence"]
    assert "expected_root_cause" not in detail.text and "scenario_name" not in detail.text
    assert client.get("/api/v1/workbench/cases", params={"status": "INVALID"}, headers=REVIEWER).status_code == 422
    assert client.get("/api/v1/workbench/cases/missing", headers=REVIEWER).status_code == 404
    assert client.get("/api/v1/workbench/cases", params={"offset": 5000}, headers=REVIEWER).json()["items"] == []


def test_workbench_permission_and_historical_model_status(session, client):
    assert client.get("/api/v1/workbench/identity", headers=REVIEWER).json()["roles"] == ["OPERATIONS_REVIEWER"]
    for endpoint in ("approvals", "memories"):
        assert client.get("/api/v1/workbench/"+endpoint, headers=WORKER).status_code == 403
        assert client.get("/api/v1/workbench/"+endpoint, headers=REVIEWER).status_code == 200
    lab = client.get("/api/v1/workbench/model-lab", headers=REVIEWER).json()
    assert lab["operational_model_enabled"] is False
    assert all(report["decision"] == "RETAIN_DETERMINISTIC" for report in lab["model_comparison"].values())
    assert "historical" in lab["checkpoint"]


def test_action_approval_remains_backend_authorized(session, client):
    parts = fixture_case(session, human=True)
    authorization = evaluate(session, parts)
    page = client.get("/api/v1/workbench/approvals", headers=REVIEWER).json()
    assert page["actions"][0]["authorization"]["policy"]["is_active"] is True
    assert page["actions"][0]["authorization"]["control_snapshot"]["source"]["bank"]["payment"]["status"] == "SETTLED"
    approval_id = page["actions"][0]["approval"]["id"]
    url = "/api/v1/action-approvals/" + approval_id + "/decision"
    request = {"operation": "APPROVE", "reason": "Actual PostgreSQL evidence reviewed"}
    assert client.post(url, json=request, headers=WORKER).status_code == 403
    assert client.post(url, json={**request, "actor": "forged"}, headers=REVIEWER).status_code == 422
    assert client.post(url, json=request, headers=REVIEWER).status_code == 200
    assert client.post("/api/v1/actions/submit", json={"authorization_id": authorization["id"]}, headers=REVIEWER).status_code == 403
    assert session.scalar(select(func.count()).select_from(ActionRecord)) == 0
