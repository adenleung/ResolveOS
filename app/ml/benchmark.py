"""CPU-only offline experiments. No serving, promotion, or artifact loading."""
import importlib.metadata
import importlib.util
import json
import os
import pickle
import platform
import time
import tracemalloc
from pathlib import Path

from app.ml.dataset import DATASET_VERSION, TASKS, digest, readiness, split_rows
from app.ml.features import FEATURE_NAMES, FEATURE_VERSION

MODELS = {"logistic_regression": "sklearn", "decision_tree": "sklearn", "random_forest": "sklearn",
          "xgboost": "xgboost", "lightgbm": "lightgbm"}
POLICY = {"version": "ml-acceptance-1.0", "minimum_macro_f1_gain": .03,
          "maximum_critical_error_increase": 0, "maximum_p95_latency_ms": 50,
          "maximum_artifact_bytes": 10_000_000, "requires_group_holdout": True,
          "requires_measured_operational_benefit": True, "requires_human_approval": True,
          "requires_positive_family_bootstrap_lower_gain": True,
          "requires_no_critical_error_increase": True, "minimum_critical_recall": .95}


def dependencies():
    result = {"python": platform.python_version()}
    for name in ("numpy", "scikit-learn", "scipy", "joblib", "threadpoolctl", "xgboost", "lightgbm"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def candidates(name, seed):
    # Imports remain optional and never add operational dependencies.
    if name == "logistic_regression":
        from sklearn.linear_model import LogisticRegression
        return [LogisticRegression(C=c, max_iter=1000, class_weight="balanced", random_state=seed) for c in (.1, 1)]
    if name == "decision_tree":
        from sklearn.tree import DecisionTreeClassifier
        return [DecisionTreeClassifier(max_depth=d, min_samples_leaf=2, class_weight="balanced", random_state=seed) for d in (3, 6)]
    if name == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return [RandomForestClassifier(n_estimators=50, max_depth=d, min_samples_leaf=2, class_weight="balanced", random_state=seed, n_jobs=1) for d in (3, 6)]
    if name == "xgboost":
        from xgboost import XGBClassifier
        return [XGBClassifier(n_estimators=50, max_depth=d, learning_rate=.1, random_state=seed, n_jobs=1, tree_method="hist") for d in (2, 4)]
    if name == "lightgbm":
        from lightgbm import LGBMClassifier
        return [LGBMClassifier(n_estimators=50, max_depth=d, num_leaves=7, learning_rate=.1, random_state=seed, n_jobs=1, verbosity=-1) for d in (2, 4)]
    raise ValueError("Unknown model")


def metrics(labels, predictions, critical, probabilities=None):
    from sklearn.metrics import classification_report, confusion_matrix, f1_score, average_precision_score, brier_score_loss
    classes = sorted(set(labels) | set(predictions))
    denominator = sum(critical)
    result = {"macro_f1": f1_score(labels, predictions, average="macro", zero_division=0),
              "per_class": classification_report(labels, predictions, labels=classes, output_dict=True, zero_division=0),
              "classes": classes, "confusion_matrix": confusion_matrix(labels, predictions, labels=classes).tolist(),
              "critical_errors": sum(c and y != p for y, p, c in zip(labels, predictions, critical)),
              "critical_examples": denominator,
              "critical_error_rate": sum(c and y != p for y, p, c in zip(labels, predictions, critical)) / denominator if denominator else None,
              "unknown_prediction_count": predictions.count("UNKNOWN_EXCEPTION"),
              "sample_count": len(labels)}
    if probabilities is not None:
        binary = [int(y == "1") for y in labels]
        result["pr_auc_average_precision"] = average_precision_score(binary, probabilities)
        result["brier_score"] = brier_score_loss(binary, probabilities)
        result["thresholds"] = {str(t): classification_report(binary, [int(p >= t) for p in probabilities], output_dict=True, zero_division=0) for t in (.25, .5, .75)}
        result["calibration_bins"] = []
        for low, high in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
            indices = [i for i, p in enumerate(probabilities) if low <= p < high]
            result["calibration_bins"].append({"lower": low, "upper": min(high, 1), "count": len(indices),
                "mean_probability": sum(probabilities[i] for i in indices) / len(indices) if indices else None,
                "observed_rate": sum(binary[i] for i in indices) / len(indices) if indices else None})
    return result


def compare(rows, task, dataset_version=DATASET_VERSION, seed=12, scenario_holdout=False):
    if task not in TASKS or dataset_version != DATASET_VERSION:
        raise ValueError("Unsupported task or dataset version")
    if task in {"sla", "risk", "correlation"} and any(r["label"] not in {"0", "1"} for r in rows):
        raise ValueError("Binary task labels must be 0 or 1")
    audit = readiness(rows)
    splits = split_rows(rows, seed, scenario_holdout) if audit["ready"] else None
    if splits:
        audit = readiness(rows, splits)
    report = {"task": task, "dataset_version": dataset_version, "dataset_sha256": digest(rows),
              "feature_version": FEATURE_VERSION, "seed": seed, "splits": splits,
              "split_strategy": "scenario_family_holdout" if scenario_holdout else "incident_family_holdout",
              "dependencies": dependencies(), "policy": POLICY, "readiness": audit,
              "hardware": {"platform": platform.platform(), "machine": platform.machine(), "logical_cpu_count": os.cpu_count()},
              "unknown_handling": "Held-out labels absent from training are rejected. Experimental estimators have no validated abstention policy; operational integration is disabled.",
              "decision": "RETAIN_DETERMINISTIC", "operational_enabled": False,
              "business_value": {k: None for k in ("specialist_calls_per_case", "llm_calls_avoided", "investigation_duration", "escalation_correctness", "human_reviews")},
              "models": {}}
    for name, module in MODELS.items():
        available = importlib.util.find_spec(module) is not None and importlib.util.find_spec("sklearn") is not None
        report["models"][name] = {"available": available, "status": "BLOCKED_DATASET" if not audit["ready"] else "UNAVAILABLE"}
    report["baseline"] = {"status": "BLOCKED_DATASET"}
    if not audit["ready"]:
        return report
    try:
        import numpy as np
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler, LabelEncoder
        from sklearn.metrics import f1_score
    except (ImportError, OSError) as exc:
        for entry in report["models"].values():
            entry.update(status="UNAVAILABLE", error=type(exc).__name__ + ": " + str(exc))
        report["baseline"] = {"status": "METRICS_LIBRARY_UNAVAILABLE"}
        return report
    train, validation, test = ([rows[i] for i in splits[name]] for name in ("train", "validation", "test"))
    def x(part):
        return [[r["features"][key] for key in FEATURE_NAMES] for r in part]
    encoder = LabelEncoder().fit([r["label"] for r in train])
    if any(r["label"] not in encoder.classes_ for r in validation + test):
        raise ValueError("Unseen labels in holdout; no supported benchmark")
    y_train = encoder.transform([r["label"] for r in train])
    y_test = [r["label"] for r in test]
    critical = [r["critical"] for r in test]
    baseline_probabilities = [float(r["baseline"]) for r in test] if task in {"sla", "risk", "correlation"} and all(r["baseline"] in {"0", "1"} for r in test) else None
    report["baseline"] = {"status": "EVALUATED", "metrics": metrics(y_test, [r["baseline"] for r in test], critical, baseline_probabilities),
                          "latency_ms": None, "note": "Baseline labels must come from frozen existing rule outputs; execution latency is not captured in dataset rows."}
    for name, entry in report["models"].items():
        if not entry["available"]:
            continue
        started = time.perf_counter()
        cpu_started = time.process_time()
        tracemalloc.start()
        try:
            best, best_score = None, -1
            for candidate in candidates(name, seed):
                model = make_pipeline(StandardScaler(), candidate)
                model.fit(x(train), y_train)
                prediction = encoder.inverse_transform(model.predict(x(validation)))
                score = f1_score([r["label"] for r in validation], prediction, average="macro", zero_division=0)
                if score > best_score:
                    best, best_score = model, score
            training_seconds = time.perf_counter() - started
            prediction = encoder.inverse_transform(best.predict(x(test))).tolist()
            probability = None
            if task in {"sla", "risk", "correlation"}:
                positive = list(encoder.classes_).index("1")
                probability = best.predict_proba(x(test))[:, positive].tolist()
            # Per-row wall latency including numeric matrix materialization; CPU only.
            latencies = []
            for row in test:
                before = time.perf_counter()
                best.predict(x([row]))
                latencies.append((time.perf_counter() - before) * 1000)
            configuration = {"dataset_sha256": report["dataset_sha256"], "task": task, "seed": seed,
                             "splits": splits, "feature_version": FEATURE_VERSION,
                             "dependencies": report["dependencies"], "parameters": best.steps[-1][1].get_params()}
            configuration_hash = digest(configuration)
            entry.update(status="EVALUATED", model_version=name + "-" + configuration_hash[:12],
                         configuration_sha256=configuration_hash,
                         parameters=best.steps[-1][1].get_params(), validation_macro_f1=best_score,
                         training_seconds=training_seconds, inference_p95_ms=float(np.percentile(latencies, 95)),
                         experiment_cpu_seconds=time.process_time() - cpu_started,
                         model_bytes=len(pickle.dumps((best, encoder))), python_peak_allocated_bytes=tracemalloc.get_traced_memory()[1],
                         metrics=metrics(y_test, prediction, critical, probability),
                         uncertainty="Small synthetic sample; no production generalization or causal benefit claim.")
            # Bootstrap complete incident families, never individual related rows.
            families = sorted({r["family"] for r in test})
            indices_by_family = {family: [i for i, row in enumerate(test) if row["family"] == family] for family in families}
            generator = np.random.default_rng(seed)
            gains = []
            for _ in range(200):
                indices = [i for family in generator.choice(families, size=len(families), replace=True) for i in indices_by_family[family]]
                truth = [y_test[i] for i in indices]
                gains.append(f1_score(truth, [prediction[i] for i in indices], average="macro", zero_division=0)
                             - f1_score(truth, [test[i]["baseline"] for i in indices], average="macro", zero_division=0))
            entry["macro_f1_gain_family_bootstrap_95_interval"] = np.percentile(gains, [2.5, 97.5]).tolist()
        except (ImportError, ValueError, RuntimeError) as exc:
            entry.update(status="FAILED", error=type(exc).__name__ + ": " + str(exc))
        finally:
            tracemalloc.stop()
    # Ranking never constitutes promotion. Operational benefit requires a separate
    # controlled measurement and human approval; this runner cannot supply either.
    return report


def write_report(report, path):
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
