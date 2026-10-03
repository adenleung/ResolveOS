from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ingestion.models import EventRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def event_reference(event: EventRecord) -> dict[str, Any]:
    return {
        "event_record_id": event.id,
        "event_id": event.event_id,
        "source_system": event.source_system,
        "event_type": event.event_type,
        "entity_reference": event.entity_reference,
        "correlation_id": event.correlation_id,
        "source_record_reference": event.source_record_reference,
        "occurred_at": _utc(event.occurred_at).isoformat(),
    }


@dataclass(slots=True)
class CaseCorrelationFeatures:
    case_id: str
    exception_ids: list[str]
    categories: set[str]
    uncertainty_flags: set[str]
    operational_eligible: bool
    evidence_complete: bool
    strong_identifiers: dict[str, set[str]] = field(default_factory=dict)
    weak_features: set[str] = field(default_factory=set)
    systems: set[str] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)
    error_families: set[str] = field(default_factory=set)
    event_times: list[datetime] = field(default_factory=list)
    evidence_references: list[dict[str, Any]] = field(default_factory=list)
    strong_evidence: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    incident_identifiers: set[str] = field(default_factory=set)

    @property
    def strong_tokens(self) -> set[str]:
        return {
            f"{feature_type}:{value}"
            for feature_type, values in self.strong_identifiers.items()
            for value in values
        }

    @property
    def time_start(self) -> datetime | None:
        return min(self.event_times) if self.event_times else None

    @property
    def time_end(self) -> datetime | None:
        return max(self.event_times) if self.event_times else None

    def summary(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "exception_ids": self.exception_ids,
            "categories": sorted(self.categories),
            "systems": sorted(self.systems),
            "dependencies": sorted(self.dependencies),
            "error_families": sorted(self.error_families),
            "strong_identifiers": {
                key: sorted(values) for key, values in sorted(self.strong_identifiers.items())
            },
            "evidence_complete": self.evidence_complete,
            "uncertainty_flags": sorted(self.uncertainty_flags),
            "operational_eligible": self.operational_eligible,
            "time_start": self.time_start.isoformat() if self.time_start else None,
            "time_end": self.time_end.isoformat() if self.time_end else None,
        }


def build_case_features(
    case_id: str,
    exception_ids: list[str],
    assessments: list[dict[str, Any]],
    events: list[EventRecord],
    linked_event_ids: set[str],
) -> CaseCorrelationFeatures:
    features = CaseCorrelationFeatures(
        case_id=case_id,
        exception_ids=exception_ids,
        categories=set(),
        uncertainty_flags=set(),
        operational_eligible=bool(assessments) and all(
            assessment.get("operational_eligible", False) for assessment in assessments
        ),
        evidence_complete=bool(linked_event_ids) and len(assessments) == len(exception_ids) and all(
            assessment.get("assessment", {}).get("priority", {}).get("input_facts", {}).get("evidence_complete", False)
            for assessment in assessments
        ),
    )
    for assessment in assessments:
        result = assessment.get("assessment", {}).get("classification", {})
        features.uncertainty_flags.update(result.get("uncertainty_flags", []))
        for item in result.get("categories", []):
            category = item.get("category")
            if category:
                features.categories.add(category)
                features.weak_features.add(f"category:{category}")
    if not assessments:
        features.categories.add("UNKNOWN_EXCEPTION")
        features.uncertainty_flags.add("missing_classification")
    if not assessments or "missing_evidence" in features.uncertainty_flags:
        features.evidence_complete = False

    ref_by_id: dict[str, dict[str, Any]] = {}
    latest_records: dict[tuple[str, str], EventRecord] = {}
    for event in events:
        key = (event.source_system, event.source_record_reference)
        previous = latest_records.get(key)
        if previous is None or (_utc(event.occurred_at), _utc(event.ingested_at), event.id) > (
            _utc(previous.occurred_at), _utc(previous.ingested_at), previous.id
        ):
            latest_records[key] = event

    def add_strong(feature_type: str, value: str | None, event: EventRecord) -> None:
        if not value:
            return
        feature_value = str(value)
        features.strong_identifiers.setdefault(feature_type, set()).add(feature_value)
        token = f"{feature_type}:{feature_value}"
        references = features.strong_evidence.setdefault(token, [])
        if all(reference["event_record_id"] != event.id for reference in references):
            references.append(event_reference(event))

    for event in events:
        if latest_records.get((event.source_system, event.source_record_reference)) != event:
            continue
        reference = event_reference(event)
        ref_by_id[event.id] = reference
        features.systems.add(event.source_system)
        features.event_times.append(_utc(event.occurred_at))
        add_strong("entity", event.entity_reference, event)
        add_strong("correlation", event.correlation_id, event)

        # Older payment envelopes copied a simulator key; it is not observed evidence.
        if event.source_system != "payments":
            incident_identifier = event.payload.get("incident_identifier")
            if incident_identifier:
                features.incident_identifiers.add(str(incident_identifier))
                add_strong("incident_identifier", str(incident_identifier), event)
            add_strong("dependency_failure_id", event.payload.get("dependency_failure_id"), event)

        if event.source_system == "api_gateway":
            service = str(event.payload.get("service_name", "unknown")).strip().lower()
            endpoint = str(event.payload.get("endpoint", "unknown")).strip().lower()
            dependency = f"{service}:{endpoint}"
            features.dependencies.add(dependency)
            features.weak_features.add(f"dependency:{dependency}")
            error_type = str(event.payload.get("error_type") or "").strip().lower()
            try:
                status_code = int(event.payload.get("status_code", 0))
                latency = int(event.payload.get("latency_ms", 0))
            except (TypeError, ValueError):
                status_code, latency = 0, 0
            if "timeout" in error_type or latency >= 30_000:
                family = "api:timeout"
            elif status_code >= 500:
                family = f"api:http_{status_code // 100}xx"
            elif error_type:
                family = f"api:{error_type}"
            else:
                family = "api:unknown"
            features.error_families.add(family)
            features.weak_features.add(f"error_family:{family}")

        if event.source_system in {"ledger", "confirmations", "workflow"}:
            features.weak_features.add(f"source_system:{event.source_system}")

    features.evidence_references = list(ref_by_id.values())
    return features
