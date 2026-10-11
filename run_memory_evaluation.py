"""Small real PostgreSQL ranking experiment with reviewed verified histories."""
import argparse
import json
import math
from pathlib import Path
import time
from sqlalchemy import select
from app.demo import WORKER, REVIEWER
from app.evaluation.database import disposable_database
from app.memory.contracts import MemoryAccess
from app.memory.service import MemoryService
from app.memory.ranking import BASELINE, OPTION_B
from app.memory.models import MemoryVersion
from app.models.domain import ExceptionRecord, PolicyVersion
from run_operational_benchmark import execute_case, seed_case


def retrieval_metrics(ids, relevant):
    hits=[int(identifier in relevant) for identifier in ids]
    first=next((index+1 for index,hit in enumerate(hits) if hit),None)
    dcg=sum(hit/math.log2(index+2) for index,hit in enumerate(hits))
    ideal=sum(1/math.log2(index+2) for index in range(min(len(relevant),len(ids))))
    return dict(precision_at_1=hits[0] if hits else 0,precision_at_3=sum(hits)/3,
        recall_at_3=sum(hits)/len(relevant) if relevant else None,
        reciprocal_rank=1/first if first else 0,ndcg_at_3=dcg/ideal if ideal else None)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="docs/hardening/artifacts/memory-evaluation.json")
    args=parser.parse_args()
    histories=[]; queries=[]
    with disposable_database() as (database,settings):
        for index,(endpoint,status) in enumerate((("/confirmations","ACTIVE"),("/payments","ACTIVE"),
                ("/confirmations","STALE_POLICY"),("/confirmations","REVOKED"))):
            spec=dict(id="memory-history-"+str(index),family="eligible_missing",amount=100,latency_ms=20,endpoint=endpoint)
            row=execute_case(database,settings,spec,"C")
            assert row["verified"]
            with database.get_session() as session:
                category=session.scalar(select(ExceptionRecord.exception_type).where(ExceptionRecord.case_id==row["case_id"]))
                request=dict(category=category,verification_id=row["records"]["verifications"][0]["id"],
                    summary="Human-reviewed synthetic replay history; current controls still required.",
                    failure_pattern="Historical observed confirmation gap",evidence_ids=[item["id"] for item in row["records"]["evidence"]][:20])
                service=MemoryService(session,settings)
                memory=service.candidate(row["case_id"],request,MemoryAccess(WORKER))
                service.review(memory["id"],dict(operation="SUBMIT",reason="Submit actual verified source"),MemoryAccess(REVIEWER))
                service.review(memory["id"],dict(operation="APPROVE",reason="Scripted synthetic reviewer; not employee judgment"),MemoryAccess(REVIEWER))
                session.commit()
                if status=="STALE_POLICY":
                    version=session.get(MemoryVersion,memory["id"])
                    session.get(PolicyVersion,version.policy_version_id).is_active=False; session.commit()
                if status=="REVOKED":
                    service.review(memory["id"],dict(operation="WITHDRAW",reason="Withdraw experiment history"),MemoryAccess(REVIEWER)); session.commit()
                histories.append(dict(id=memory["id"],endpoint=endpoint,status=status))
        for index,endpoint in enumerate(["/confirmations","/payments","/unknown"]*4):
            spec=dict(id="memory-query-"+str(index),family="eligible_missing",amount=75,latency_ms=20,endpoint=endpoint)
            with database.get_session() as session:
                case_id,_=seed_case(session,spec)
                relevant={row["id"] for row in histories if row["endpoint"]==endpoint and row["status"]=="ACTIVE"}
                for algorithm in (BASELINE,OPTION_B):
                    started=time.monotonic()
                    result=MemoryService(session,settings).retrieve(case_id,category,MemoryAccess(WORKER),
                        source_systems={"payments","ledger","api_gateway"},top_k=3,context_bytes=16000,ranking_version=algorithm)
                    session.commit()
                    ids=[row["id"] for row in result["memories"]]
                    assert not any(row["id"] in ids for row in histories if row["status"]=="REVOKED")
                    queries.append(dict(query_id=spec["id"],endpoint=endpoint,algorithm=algorithm,returned=ids,
                        relevant=sorted(relevant),latency_seconds=time.monotonic()-started,context_bytes=len(json.dumps(result).encode()),
                        metrics=retrieval_metrics(ids,relevant),guidance_statuses=[row["guidance_status"] for row in result["memories"]]))
        summary={}
        for algorithm in (BASELINE,OPTION_B):
            rows=[row for row in queries if row["algorithm"]==algorithm]
            summary[algorithm]={metric:sum(values)/len(values) if values else None for metric in rows[0]["metrics"]
                for values in [[row["metrics"][metric] for row in rows if row["metrics"][metric] is not None]]}
            summary[algorithm]["invalid_memory_retrieval_rate"]=0
        document=dict(version="memory-evaluation-1.0",histories=histories,queries=queries,summary=summary,
            decision="Retain original runtime default; Option B available explicitly for further evaluation",
            limitations=["Four synthetic reviewed histories, 12 correlated queries, one run", "No live investigation benefit measured",
                "No causal root-cause labels", "No statistical significance claim", "No-match queries expose both algorithms' false relevance limitations"])
        output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(document,indent=2,default=str)+"\n",encoding="utf-8")
        print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
