"""Read-only intake extraction from existing PostgreSQL evidence links."""
from datetime import timedelta
from sqlalchemy import select
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import Case, ExceptionRecord
from app.classification.rules import RuleBasedClassifier
from app.ml.features import extract_features, available_events, utc


def intake_snapshot(session, exception_id, prediction_at, confirmation_seconds=300, workflow_seconds=1800):
    cutoff = utc(prediction_at)
    exception = session.get(ExceptionRecord, exception_id)
    if exception is None or exception.detected_at is None or utc(exception.detected_at) > cutoff:
        raise ValueError("Exception was unavailable at prediction time")
    case = session.get(Case, exception.case_id)
    if case is None or utc(case.created_at) > cutoff:
        raise ValueError("Case was unavailable at prediction time")
    events = session.execute(select(EventRecord).join(ExceptionEvidence,
        ExceptionEvidence.event_record_id == EventRecord.id).where(
        ExceptionEvidence.exception_id == exception_id, ExceptionEvidence.linked_at <= cutoff,
        EventRecord.occurred_at <= cutoff, EventRecord.ingested_at <= cutoff)).scalars().all()
    visible = available_events(events, cutoff)
    baseline = RuleBasedClassifier().classify(exception.exception_type, visible, cutoff,
        timedelta(seconds=confirmation_seconds), timedelta(seconds=workflow_seconds), not bool(visible))
    return {"features": extract_features(visible, case.created_at, cutoff),
            "baseline": "|".join(sorted(item["category"] for item in baseline["categories"])),
            "baseline_version": baseline["rule_version"], "prediction_at": cutoff.isoformat(),
            "action_authorization": "NOT_EVALUATED"}
