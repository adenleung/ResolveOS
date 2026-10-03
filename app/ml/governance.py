"""Experimental registration metadata, deliberately without promotion APIs."""
import re
from app.ml.benchmark import MODELS, POLICY
from app.ml.dataset import DATASET_VERSION, digest
from app.ml.features import FEATURE_VERSION


def registration(report, name):
    if name not in MODELS:
        raise ValueError("Unsupported model")
    entry = report["models"][name]
    version = entry.get("model_version", "")
    if entry["status"] != "EVALUATED" or not re.fullmatch(re.escape(name) + r"-[0-9a-f]{12}", version):
        raise ValueError("Untrained or invalid model version")
    if report["feature_version"] != FEATURE_VERSION or report["dataset_version"] != DATASET_VERSION or report["policy"] != POLICY:
        raise ValueError("Incompatible artifact metadata")
    if version != name + "-" + entry.get("configuration_sha256", "")[:12]:
        raise ValueError("Artifact dataset mismatch")
    expected_configuration = {"dataset_sha256": report["dataset_sha256"], "task": report["task"], "seed": report["seed"],
                              "splits": report["splits"], "feature_version": report["feature_version"],
                              "dependencies": report["dependencies"], "parameters": entry.get("parameters")}
    if entry.get("configuration_sha256") != digest(expected_configuration):
        raise ValueError("Configuration content mismatch")
    return {"model_version": version, "feature_version": FEATURE_VERSION,
            "dataset_version": DATASET_VERSION, "dataset_sha256": report["dataset_sha256"],
            "report_sha256": digest(report), "dependencies": report["dependencies"],
            "status": "EXPERIMENTAL", "operational_enabled": False,
            "action_authorization": "NOT_EVALUATED"}
