"""Read-only dataset audit and blocked benchmark acceptance for existing data.

Usage: set DATABASE_URL, then python verify_phase12.py.
No source rows, credentials, identifiers, or trained artifacts are exported.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from app.config import get_settings
from app.ml.benchmark import compare, write_report
from app.ml.dataset import TASKS
from app.simulator.service import SCENARIO_DEFINITIONS


def audit_database(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        counts = {table: connection.execute(text("SELECT count(*) FROM " + table)).scalar_one() for table in (
            "sim_payments", "sim_ledger_entries", "sim_confirmation_events", "sim_technology_logs", "sim_workflow_states",
            "event_records", "exceptions", "cases", "assessment_history", "investigation_runs", "verification_results")}
        payments = connection.execute(text("SELECT scenario_name, expected_root_cause, processing_outcome, incident_key, status, amount FROM sim_payments")).mappings().all()
        event_stats = connection.execute(text("SELECT source_system, count(*) AS count, min(occurred_at) AS first_occurred, max(occurred_at) AS last_occurred, min(ingested_at) AS first_ingested, max(ingested_at) AS last_ingested FROM event_records GROUP BY source_system ORDER BY source_system")).mappings().all()
        exception_distribution = dict(connection.execute(text("SELECT exception_type, count(*) FROM exceptions GROUP BY exception_type")).all())
        # Schema-level provenance audit: none of these operational tables provides
        # reviewed task-specific annotation contracts or trajectory instrumentation.
        duplicates = connection.execute(text("SELECT count(*) - count(DISTINCT (source_system,event_id)) FROM event_records")).scalar_one()
        future = connection.execute(text("SELECT count(*) FROM event_records WHERE occurred_at > CURRENT_TIMESTAMP OR ingested_at > CURRENT_TIMESTAMP")).scalar_one()
        missing = {field: sum(row[field] is None for row in payments) for field in ("scenario_name", "expected_root_cause", "processing_outcome", "incident_key")}
        shapes = Counter((r["scenario_name"], r["status"]) for r in payments)
        transaction.rollback()
    report = {"audit_version": "dataset-readiness-1.0", "audited_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision, "counts": counts, "scenario_templates": len(SCENARIO_DEFINITIONS),
        "distinct_observed_scenarios": len({r["scenario_name"] for r in payments}),
        "observed_scenario_distribution": dict(Counter(r["scenario_name"] for r in payments)),
        "simulator_family_keys": len({r["incident_key"] for r in payments if r["incident_key"]}),
        "validated_independent_incident_families": 0,
        "missing_simulator_fields": missing, "exact_duplicate_event_identities": duplicates,
        "near_duplicate_payment_shapes_excluding_amount_and_identifiers": sum(v - 1 for v in shapes.values()),
        "future_dated_events": future, "exception_type_distribution": exception_distribution,
        "source_timing": [dict(r) for r in event_stats],
        "usable_validated_training_examples": {task: 0 for task in TASKS},
        "ready": False,
        "label_provenance": "Simulator expected_root_cause and processing_outcome are hidden template labels, not validated task targets. Rule assessments are baseline outputs, not independent ground truth. Investigator text and reviewed memory are not training labels.",
        "blocking_findings": ["Only two source payments at the inspected checkpoint; insufficient incident-family diversity even if all were labelled.",
            "No validated task-specific label dataset or split manifest exists.",
            "Scenario names occur in identifiers; template statuses, fixed log patterns and ledger deltas offer memorization shortcuts.",
            "Simulator uses wall-clock generation; seed alone does not reproduce timestamps.",
            "SLA outcome trajectories, independently reviewed routing utility, risk escalation targets, and pairwise incident causation labels are absent.",
            "Distribution and temporal generalization cannot be estimated from this small checkpoint."]}
    # Do not hard-code the observed row count into findings for subsequent audits.
    report["blocking_findings"][0] = f"{counts['sim_payments']} source payments; independence not validated and no adequate family coverage established."
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="phase12-dataset-readiness.json")
    parser.add_argument("--benchmark-output", default="phase12-model-comparison.json")
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url)
    try:
        report = audit_database(engine)
    finally:
        engine.dispose()
    Path(args.output).write_text(json.dumps(report, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")
    benchmarks = {task: compare([], task) for task in TASKS}
    write_report(benchmarks, args.benchmark_output)
    assert not report["ready"] and all(not r["operational_enabled"] for r in benchmarks.values())
    print(json.dumps({"revision": report["revision"], "counts": report["counts"], "ready": False, "decision": "RETAIN_DETERMINISTIC"}))


if __name__ == "__main__":
    main()
