"""Offline component-unavailability ablation through the existing durable worker."""
import argparse
import json
from pathlib import Path
import time
from sqlalchemy import select
from app.demo import ObservedDemoSpecialist, ObservedDemoSupervisor
from app.evaluation.database import disposable_database
from app.evaluation.records import case_records
from app.investigation.provider import ProviderError
from app.orchestration.worker import run_once
from run_operational_benchmark import seed_case


class OmitSpecialist(ObservedDemoSpecialist):
    def __init__(self,role):self.role=role
    @property
    def identifier(self):return "offline-ablation-omit-"+self.role
    def turn(self,instructions,messages,tools,max_tokens):
        if json.loads(messages[0]["content"])["role"]==self.role:
            raise ProviderError("ablation_component_unavailable")
        return super().turn(instructions,messages,tools,max_tokens)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="docs/hardening/artifacts/agent-ablation.json")
    args=parser.parse_args()
    rows=[]
    for config in ("existing-routing","omit-transaction","omit-technology","omit-risk","omit-supervisor"):
        with disposable_database() as (database,settings):
            for family in ("eligible_missing","technology_timeout"):
                started=time.monotonic()
                with database.get_session() as session:
                    case_id,_=seed_case(session,dict(id=config+"-"+family,family=family,amount=100,latency_ms=20))
                omitted=config.removeprefix("omit-").upper()
                provider=OmitSpecialist(omitted) if omitted in {"TRANSACTION","TECHNOLOGY","RISK"} else ObservedDemoSpecialist()
                supervisor=None if config=="omit-supervisor" else ObservedDemoSupervisor()
                for _ in range(50):
                    result=run_once(database,"offline-ablation-worker",settings,provider=provider,supervisor_provider=supervisor)
                    if result["claimed"]==0:break
                else:raise RuntimeError("ablation_worker_bound_exceeded")
                with database.get_session() as session:
                    record=case_records(session,case_id)
                rows.append(dict(configuration=config,family=family,elapsed_seconds=time.monotonic()-started,
                    final_state=record["final_state"],specialist_invocations=len(record["investigations"]),
                    tool_calls=sum(len(row["telemetry"].get("tools",[])) for row in record["investigations"]),
                    supervisor_records=len(record["supervisor"]),protected_effects=len(record["operations"]),records=record))
                assert not record["operations"] and record["final_state"]!="RESOLVED"
    document=dict(version="agent-ablation-1.0",mode="OFFLINE_COMPONENT_UNAVAILABILITY",rows=rows,
        conclusion="Retain existing routing; omitted required components lose review readiness without gaining supported resolution",
        limitations=["Two synthetic families and one run per configuration", "No live-model accuracy/quality ablation",
            "Omitted specialists fail explicitly; this tests failure containment, not a proposed leaner production workflow",
            "No action submitted in any configuration; resolution coverage is not assessed in this experiment"])
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(document,indent=2,default=str)+"\n",encoding="utf-8")
    print([(row["configuration"],row["family"],row["final_state"]) for row in rows])


if __name__=="__main__":main()
