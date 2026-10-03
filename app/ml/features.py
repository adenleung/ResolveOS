"""Versioned, point-in-time numeric features from normalized event records."""
from datetime import datetime, timezone
import math

FEATURE_VERSION = "observed-intake-1.0"
SOURCES = ("payments", "ledger", "confirmations", "api_gateway", "workflow")
FEATURE_NAMES = tuple("count_" + source for source in SOURCES) + (
    "system_count", "api_failure_count", "api_timeout_count", "case_age_seconds",
    "event_span_seconds", "evidence_available",
)


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An explicit timezone is required")
    return value.astimezone(timezone.utc)


def validate_features(features, version=FEATURE_VERSION):
    if version != FEATURE_VERSION or set(features) != set(FEATURE_NAMES):
        raise ValueError("Incompatible feature schema")
    for value in features.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Features must be finite nonnegative numbers")
    for name in FEATURE_NAMES:
        if name.startswith("count_") or name in {"system_count", "api_failure_count", "api_timeout_count", "evidence_available"}:
            if int(features[name]) != features[name]:
                raise ValueError("Counts must be integers")
    if features["evidence_available"] not in (0, 1) or features["system_count"] > len(SOURCES):
        raise ValueError("Invalid feature bounds")
    return features


def available_events(events, prediction_at):
    cutoff = utc(prediction_at)
    visible = []
    for event in events:
        occurred, ingested = utc(event.occurred_at), utc(event.ingested_at)
        if occurred <= cutoff and ingested <= cutoff:
            if event.source_system not in SOURCES or not isinstance(event.payload, dict):
                raise ValueError("Unsupported or malformed event")
            visible.append(event)
    # Latest record as known at cutoff, not the latest record now.
    latest = {}
    for event in visible:
        key = (event.source_system, event.source_record_reference)
        rank = (utc(event.occurred_at), utc(event.ingested_at), event.id)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, event)
    return [item[1] for _, item in sorted(latest.items())]


def extract_features(events, created_at, prediction_at):
    cutoff, created = utc(prediction_at), utc(created_at)
    if created > cutoff:
        raise ValueError("Case did not yet exist")
    visible = available_events(events, prediction_at)
    features = {name: 0 for name in FEATURE_NAMES}
    times = []
    for event in visible:
        features["count_" + event.source_system] += 1
        times.append(utc(event.occurred_at))
        if event.source_system == "api_gateway":
            status = event.payload.get("status_code")
            latency = event.payload.get("latency_ms")
            if type(status) is not int or not 100 <= status <= 599 or type(latency) is not int or latency < 0:
                raise ValueError("Malformed API observation")
            features["api_failure_count"] += int(status >= 500)
            features["api_timeout_count"] += int(latency >= 30000 or "timeout" in str(event.payload.get("error_type", "")).lower())
    features["system_count"] = len({event.source_system for event in visible})
    features["case_age_seconds"] = (cutoff - created).total_seconds()
    features["event_span_seconds"] = (max(times) - min(times)).total_seconds() if times else 0
    features["evidence_available"] = int(bool(visible))
    return validate_features(features)
