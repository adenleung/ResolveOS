"""Fresh real-service journeys with machine-readable evidence, no frontend or live AI."""
import argparse
import json
from pathlib import Path
from app.demo import build_journeys, verify_journeys
from app.evaluation.database import disposable_database
from app.evaluation.records import case_records
from app.intelligence.service import IntelligenceService
from app.intelligence.contracts import AnalyticsAccess
from app.demo import REVIEWER
from run_operational_benchmark import execute_case


def main():
    parser = argparse.ArgumentParser()
    extra = {"duplicate-request":"duplicate_delivery", "worker-interruption":"worker_restart",
        "verification-failure":"verification_failure", "missing-handler":"unsupported_workflow"}
    parser.add_argument("--scenario", choices=("all", "verified-resolution", "contradictory-evidence", "stale-authorization", *extra), default="all")
    parser.add_argument("--output", default="docs/hardening/artifacts/headless-demo.json")
    args = parser.parse_args()
    with disposable_database() as (database, settings):
        manifest = build_journeys(database, settings, correlate=True)
        verify_journeys(database, manifest)
        selected = {"verified-resolution": "A", "contradictory-evidence": "B", "stale-authorization": "C"}.get(args.scenario)
        with database.get_session() as session:
            records = {label: case_records(session, row["case_id"]) for label, row in manifest["journeys"].items()
                if args.scenario == "all" or label == selected}
        for label,family in extra.items():
            if args.scenario not in {"all",label}: continue
            observed=execute_case(database,settings,dict(id="headless-"+label,family=family,amount=100,latency_ms=20),"C")
            if family in {"duplicate_delivery","worker_restart"}: assert observed["verified"]
            else: assert not observed["verified"]
            if family=="verification_failure": assert observed["final_state"]=="ESCALATED"
            if family=="unsupported_workflow": assert any(row["status"]=="WAITING_HANDLER" and row["task_type"] in {"INVESTIGATE_WORKFLOW","INVESTIGATE_DOCUMENT"} for row in observed["records"]["tasks"])
            records[label]=observed["records"]
        with database.get_session() as session:
            intelligence = IntelligenceService(session, AnalyticsAccess(REVIEWER)).report().model_dump(mode="json")
        # This helper creates no development connection for writes. Remove the
        # inherited fixture assertion: no persistent row-hash study was performed.
        manifest["verified_assertions"].pop("development_untouched", None)
        result = dict(version="headless-1.0", provider_mode="OFFLINE_DETERMINISTIC", manifest=manifest,
            records=records, intelligence=intelligence, database_lifecycle="disposable; removed on exit")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        for label, record in records.items():
            print(label, record["case_id"], record["final_state"], "tasks", len(record["tasks"]),
                "evidence", len(record["evidence"]), "verifications", len(record["verifications"]))
    print("Evidence exported; disposable database removed:", args.output)


if __name__ == "__main__":
    main()
