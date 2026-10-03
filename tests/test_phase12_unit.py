from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import copy
import pytest

from app.ml.features import extract_features, validate_features, FEATURE_VERSION
from app.ml.dataset import split_rows, readiness, digest, validate_rows
from app.ml.benchmark import compare, MODELS
from app.ml.governance import registration

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def event(**changes):
    values = dict(id="e", source_system="api_gateway", source_record_reference="r",
                  occurred_at=NOW - timedelta(seconds=5), ingested_at=NOW - timedelta(seconds=2),
                  payload={"status_code": 504, "latency_ms": 31000, "scenario_name": "secret"})
    return SimpleNamespace(**(values | changes))


def rows(n=60):
    feature = extract_features([], NOW, NOW)
    return [dict(id=str(i), family=str(i), scenario="s" + str(i // 10), prediction_at=NOW.isoformat(),
                 features=dict(feature), label=str(i % 2), baseline="0", critical=bool(i % 2),
                 label_provenance="reviewed_synthetic_annotation") for i in range(n)]


def test_features_deterministic_and_no_payload_shortcuts():
    first = extract_features([event()], NOW - timedelta(seconds=10), NOW)
    other = event(payload={"status_code": 504, "latency_ms": 31000, "scenario_name": "changed", "expected_root_cause": "future", "resolution": "success"})
    assert first == extract_features([other], NOW - timedelta(seconds=10), NOW)
    assert first["api_timeout_count"] == first["api_failure_count"] == 1


@pytest.mark.parametrize("field", ["occurred_at", "ingested_at"])
def test_future_events_excluded(field):
    assert extract_features([event(**{field: NOW + timedelta(seconds=1)})], NOW, NOW)["evidence_available"] == 0


def test_historical_latest_snapshot_and_input_order():
    old = event(id="old")
    late = event(id="new", ingested_at=NOW + timedelta(seconds=1))
    assert extract_features([late, old], NOW, NOW) == extract_features([old], NOW, NOW)
    assert extract_features([old, late], NOW, NOW) == extract_features([late, old], NOW, NOW)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, "3", None, True, .5])
def test_malformed_counts(value):
    feature = extract_features([], NOW, NOW)
    feature["api_failure_count"] = value
    with pytest.raises(ValueError):
        validate_features(feature)


def test_missing_features_schema_and_naive_dates():
    with pytest.raises(ValueError):
        validate_features({})
    with pytest.raises(ValueError):
        validate_features(extract_features([], NOW, NOW), "wrong")
    with pytest.raises(ValueError):
        extract_features([], NOW.replace(tzinfo=None), NOW)
    with pytest.raises(ValueError):
        extract_features([], NOW + timedelta(seconds=1), NOW)


@pytest.mark.parametrize("payload", [{}, {"status_code": "504", "latency_ms": 1}, {"status_code": 504, "latency_ms": -1}])
def test_malformed_observations(payload):
    with pytest.raises(ValueError):
        extract_features([event(payload=payload)], NOW, NOW)


def test_groups_never_cross_splits_and_seed_reproducible():
    data = rows()
    data.extend([dict(r, id=r["id"] + "related") for r in data[:10]])
    splits = split_rows(data)
    assert splits == split_rows(data)
    assert splits != split_rows(data, seed=13)
    groups = [{data[i]["family"] for i in indices} for indices in splits.values()]
    assert not groups[0] & groups[1] and not groups[1] & groups[2] and not groups[0] & groups[2]


def test_scenario_holdout_and_unseen_families():
    data = rows()
    splits = split_rows(data, scenario_holdout=True)
    scenarios = [{data[i]["scenario"] for i in indices} for indices in splits.values()]
    assert all(not left & right for index, left in enumerate(scenarios) for right in scenarios[index + 1:])


def test_inadequate_data_and_imbalance_block_training():
    data = rows()
    data[-1]["label"] = "rare"
    assert not readiness(data)["ready"]
    assert not readiness([])["ready"]
    with pytest.raises(ValueError):
        split_rows(rows(2))


@pytest.mark.parametrize("task", ["classification", "sla", "routing", "risk", "correlation"])
def test_blocked_experiments_reproducible_and_no_authorization(task, monkeypatch):
    import app.ml.benchmark as benchmark
    monkeypatch.setattr(benchmark, "candidates", lambda *a: pytest.fail("Training must not run"))
    report = compare([], task)
    assert report == compare([], task)
    assert report["decision"] == "RETAIN_DETERMINISTIC"
    assert not report["operational_enabled"]
    assert all(r["status"] == "BLOCKED_DATASET" for r in report["models"].values())
    assert report["baseline"]["status"] == "BLOCKED_DATASET"
    assert all(value is None for value in report["business_value"].values())


@pytest.mark.parametrize("name", list(MODELS))
def test_untrained_artifacts_rejected(name):
    with pytest.raises(ValueError):
        registration(compare([], "classification"), name)


@pytest.mark.parametrize("change", [{"label_provenance": "unreviewed_ai"}, {"unexpected": "hidden"}, {"critical": "true"}])
def test_unreviewed_labels_and_extra_fields_rejected(change):
    data = rows(1)
    data[0].update(change)
    with pytest.raises(ValueError):
        validate_rows(data)


def test_fingerprint_changes_with_features_and_labels():
    data = rows(1)
    changed = copy.deepcopy(data)
    changed[0]["label"] = "changed"
    assert digest(data) != digest(changed)


def test_operational_imports_have_no_ml_dependency():
    from pathlib import Path
    for directory in ("classification", "correlation", "controls", "execution", "memory", "orchestration", "investigation", "supervisor"):
        for path in (Path("app") / directory).glob("*.py"):
            assert "app.ml" not in path.read_text(encoding="utf-8")


def test_adequate_declared_data_with_unavailable_library_retains_rules(monkeypatch):
    import builtins
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("fixture: missing numeric runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    report = compare(rows(160), "classification")
    assert report["readiness"]["ready"]
    assert all(entry["status"] == "UNAVAILABLE" for entry in report["models"].values())
    assert report["decision"] == "RETAIN_DETERMINISTIC" and not report["operational_enabled"]


@pytest.mark.parametrize("field", ["feature_version", "dataset_version", "policy", "model_version", "configuration_sha256"])
def test_experimental_registration_compatibility(field):
    report = compare([], "classification")
    name = "decision_tree"
    configuration = {key: report[key] for key in ("dataset_sha256", "task", "seed", "splits", "feature_version", "dependencies")}
    configuration["parameters"] = {}
    configuration_hash = digest(configuration)
    report["models"][name] = {"status": "EVALUATED", "model_version": name + "-" + configuration_hash[:12], "configuration_sha256": configuration_hash, "parameters": {}}
    result = registration(report, name)
    assert result["status"] == "EXPERIMENTAL" and not result["operational_enabled"]
    assert result["action_authorization"] == "NOT_EVALUATED"
    if field in {"model_version", "configuration_sha256"}:
        report["models"][name][field] = "invalid"
    else:
        report[field] = "invalid"
    with pytest.raises(ValueError):
        registration(report, name)
