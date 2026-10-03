"""Explicit synthetic dataset contracts and incident/scenario aware partitions."""
from collections import Counter, defaultdict
import hashlib
import json
import random

from app.ml.features import FEATURE_VERSION, validate_features, utc

TASKS = ("classification", "sla", "routing", "risk", "correlation")
DATASET_VERSION = "synthetic-evaluation-1.0"
LABEL_PROVENANCE = {"reviewed_synthetic_annotation", "independent_simulator_outcome"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_rows(rows):
    ids = set()
    for row in rows:
        required = {"id", "family", "scenario", "prediction_at", "features", "label", "label_provenance", "baseline", "critical"}
        if set(row) != required or any(not isinstance(row[k], str) or not row[k] for k in ("id", "family", "scenario", "label", "baseline")):
            raise ValueError("Invalid dataset row")
        if row["id"] in ids or row["label_provenance"] not in LABEL_PROVENANCE or type(row["critical"]) is not bool:
            raise ValueError("Duplicate ID or unvalidated label")
        from datetime import datetime
        utc(datetime.fromisoformat(row["prediction_at"]))
        ids.add(row["id"])
        validate_features(row["features"])


def split_rows(rows, seed=12, scenario_holdout=False):
    validate_rows(rows)
    # Union scenario families when requested, also preserves incident families
    # spanning multiple scenarios. Negative pairs must already carry connected
    # component IDs over BOTH endpoint families.
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["family"]].append(index)
    if scenario_holdout:
        merged = []
        for indices in groups.values():
            scenarios = {rows[i]["scenario"] for i in indices}
            hits = [part for part in merged if part[0] & scenarios]
            for part in hits:
                scenarios |= part[0]
                indices = indices + part[1]
                merged.remove(part)
            merged.append((scenarios, indices))
        units = [sorted(indices) for _, indices in merged]
    else:
        units = list(groups.values())
    units.sort(key=lambda indices: sorted(rows[i]["id"] for i in indices))
    if len(units) < 3:
        raise ValueError("At least three independent partition units required")
    random.Random(seed).shuffle(units)
    n = len(units)
    train_end = min(n - 2, max(1, int(n * .6)))
    validation_end = min(n - 1, max(train_end + 1, int(n * .8)))
    return {name: sorted(i for unit in selected for i in unit) for name, selected in (
        ("train", units[:train_end]), ("validation", units[train_end:validation_end]), ("test", units[validation_end:]))}


def readiness(rows, splits=None):
    validate_rows(rows)
    classes = sorted({r["label"] for r in rows})
    family_classes = {label: len({r["family"] for r in rows if r["label"] == label}) for label in classes}
    reasons = []
    if len(classes) < 2:
        reasons.append("fewer_than_two_label_classes")
    if any(count < 30 for count in family_classes.values()) or not rows:
        reasons.append("fewer_than_30_independent_families_per_class")
    if splits is not None:
        for name, indices in splits.items():
            for label in classes:
                if len({rows[i]["family"] for i in indices if rows[i]["label"] == label}) < (10 if name == "train" else 5):
                    reasons.append(f"insufficient_{name}_{label}")
    fingerprints = Counter(digest(r["features"]) for r in rows)
    return {"usable_rows": len(rows), "incident_families": len({r["family"] for r in rows}),
            "class_distribution": dict(Counter(r["label"] for r in rows)), "independent_families_per_class": family_classes,
            "duplicate_feature_rows": sum(c - 1 for c in fingerprints.values()),
            "ready": not reasons, "blocking_reasons": reasons}
