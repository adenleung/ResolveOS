"""Optional estimator smoke checks; toy fixtures are NOT ResolveOS benchmarks.

Run with optional requirements-ml.txt installed. No DB, LLM or banking effects.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from app.ml.benchmark import compare, metrics, POLICY
from app.ml.dataset import DATASET_VERSION, TASKS
from app.ml.features import extract_features, FEATURE_VERSION
from app.ml.governance import registration


def main():
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    rows = []
    for i in range(160):
        features = extract_features([], now, now)
        features["case_age_seconds"] = i % 2 * 100 + (i % 7)
        rows.append(dict(id=str(i), family=str(i), scenario=str(i // 10), prediction_at=now.isoformat(),
                         features=features, label=str(i % 2), baseline="0", critical=bool(i % 2),
                         label_provenance="reviewed_synthetic_annotation"))
    checked = []
    for task in TASKS:
        report = compare(rows, task)
        if any(report["models"][name]["status"] == "UNAVAILABLE" for name in ("logistic_regression", "decision_tree", "random_forest")):
            result = {"status": "BLOCKED", "purpose": "Optional toy estimator checks; not a ResolveOS benchmark",
                      "dependencies": report["dependencies"], "models": report["models"], "operational_enabled": False}
            Path("phase12-framework-smoke.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("Optional estimator validation blocked: " + next(iter(report["models"].values()))["error"])
            return 2
        for name in ("logistic_regression", "decision_tree", "random_forest"):
            entry = report["models"][name]
            assert entry["status"] == "EVALUATED", entry
            assert entry["metrics"]["sample_count"] == len(report["splits"]["test"])
            assert len(entry["macro_f1_gain_family_bootstrap_95_interval"]) == 2
            record = registration(report, name)
            assert not record["operational_enabled"] and record["action_authorization"] == "NOT_EVALUATED"
            checked.append(task + ":" + name)
        if task in {"sla", "risk", "correlation"}:
            assert "brier_score" in report["models"]["logistic_regression"]["metrics"]
            assert len(report["models"]["logistic_regression"]["metrics"]["calibration_bins"]) == 5
        repeated = compare(rows, task)
        for name in ("logistic_regression", "decision_tree", "random_forest"):
            assert report["models"][name]["metrics"] == repeated["models"][name]["metrics"]
            assert report["models"][name]["parameters"] == repeated["models"][name]["parameters"]
        assert report["splits"] == repeated["splits"]
        for field in ("feature_version", "dataset_version"):
            changed = copy.deepcopy(report)
            changed[field] = "invalid"
            try:
                registration(changed, "logistic_regression")
            except ValueError:
                pass
            else:
                raise AssertionError("Compatibility check failed")
    result = {"status": "PASSED", "purpose": "Toy estimator framework smoke checks only; no ResolveOS performance claims",
              "checked": checked, "reproducible_predictions": True,
              "optional_boosters": "unavailable; not installed", "operational_enabled": False}
    Path("phase12-framework-smoke.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
