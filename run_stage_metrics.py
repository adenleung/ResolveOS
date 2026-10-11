"""Derive only supported stage durations from the observed benchmark trace export."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from app.evaluation.metrics import durations


def timestamp(value):return datetime.fromisoformat(value)
def interval(start,end):
    value=(timestamp(end)-timestamp(start)).total_seconds()
    return value if value>=0 else None


def stage_metrics(record):
    histories=record["task_events"]
    queue=[]; supervisor=[]; execution=[]; verification=[]; approval=[]
    for task in record["tasks"]:
        if task["task_type"] in {"CHECK_SLA","REQUEST_HUMAN_REVIEW"}:continue
        events=sorted([row for row in histories if row["task_id"]==task["id"]],key=lambda row:row["created_at"])
        created=next((row for row in events if row["event_type"]=="task_created"),None)
        eligible=created if created and created["details"].get("handler_available") else next((row for row in events
            if row["event_type"] in {"investigator_handler_registered","supervisor_handler_registered"}),None)
        claimed=next((row for row in events if row["event_type"]=="task_claimed"),None)
        if eligible:queue.append(interval(eligible["created_at"],claimed["created_at"]) if claimed else None)
    investigation=[interval(row["started_at"],row["completed_at"]) if row["completed_at"] else None for row in record["investigations"]]
    for review in record["supervisor"]:
        task_id=review["result"].get("task_id")
        start=next((row for row in histories if row["task_id"]==task_id and row["event_type"]=="supervisor_started"),None)
        supervisor.append(interval(start["created_at"],review["created_at"]) if start else None)
    for operation in record["operations"]:
        effects=[row for row in histories if row["event_type"]=="execution_task_completed"
            and row["details"].get("action_id")==operation["action_id"] and row["details"].get("outcome")=="EFFECT_COMMITTED"]
        if not effects:continue
        effect=max(effects,key=lambda row:row["created_at"])
        claim=next((row for row in histories if row["task_id"]==effect["task_id"] and row["event_type"]=="task_claimed"),None)
        execution.append(interval(claim["created_at"],effect["created_at"]) if claim else None)
        checked=[row for row in histories if row["event_type"]=="execution_task_completed"
            and row["details"].get("action_id")==operation["action_id"] and row["details"].get("outcome") in {"VERIFIED","FAILED_VERIFICATION"}]
        verification.append(interval(effect["created_at"],max(checked,key=lambda row:row["created_at"])["created_at"]) if checked else None)
    for request in record["approvals"]:
        approved=next((row for row in record["audit"] if row["event_type"]=="action_approval_approve" and row["details"].get("approval_id")==request["id"]),None)
        approval.append(interval(request["created_at"],approved["created_at"]) if approved else None)
    detection=interval(min(row["ingested_at"] for row in record["source_events"]),record["created_at"])
    return dict(detection=[detection],first_eligible_queue_wait=queue,investigation_attempt=investigation,
        supervisor_processing=supervisor,scripted_action_approval_wait=approval,execution_processing=execution,
        independent_verification_latency=verification)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",default="docs/hardening/artifacts/operational.json")
    parser.add_argument("--output",default="docs/hardening/artifacts/stage-metrics.json")
    args=parser.parse_args()
    document=json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows=[dict(id=row["id"],mode=row["mode"],case_id=row["case_id"],metrics=stage_metrics(row["records"])) for row in document["rows"]]
    summary={mode:{key:durations([value for row in rows if row["mode"]==mode for value in row["metrics"][key]])
        for key in rows[0]["metrics"]} for mode in "ABC"}
    result=dict(version="stage-metrics-1.0",summary=summary,rows=rows,definitions=dict(
        detection="First accepted source ingestion to persisted case creation; artificial past source time is excluded",
        first_eligible_queue_wait="Initial immediate-task eligibility (creation or handler registration) to first claim; SLA timers/human review and later retry waits excluded",
        investigation_attempt="InvestigationRun started_at to completed_at, including failed attempts where recorded",
        supervisor_processing="Recorded supervisor start to review record creation; no provider-only latency claim",
        scripted_action_approval_wait="Action request creation to scripted approval audit; no employee active time or real wait estimate",
        execution_processing="Execution task claim to fenced effect task-completion record, excluding independent verification",
        independent_verification_latency="Effect task-completion record to independent verification task-completion, including queue delay and failed verification"),
        limitations=["No timestamp is replaced with zero when unavailable", "Record timestamps precede their final transaction commits",
            "Queue figure excludes subsequent retry waiting", "Approval combines database clock and application audit clock; negative intervals are unknown",
            "Supervisor/task IDs are matched explicitly; durations do not verify narrative correctness"])
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("Persisted stage metrics derived for",len(rows),"case observations")


if __name__=="__main__":main()
