"""Trusted read-only CLI aggregate diagnostics; no raw SQL URLs or source payloads."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text
from app.config import Settings


def collect(engine):
    with engine.connect() as connection:
        transaction=connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout='5s'"))
        result=dict(collected_at=datetime.now(timezone.utc).isoformat(),
            postgres_version=connection.execute(text("SHOW server_version")).scalar_one(),
            migration_head=connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one(),
            tasks=[dict(row) for row in connection.execute(text("SELECT status,task_type,count(*) AS count,max(attempt_count) AS max_attempts, min(created_at) AS oldest_created_at FROM orchestration_tasks GROUP BY status,task_type ORDER BY status,task_type")).mappings()],
            expired_running_leases=connection.execute(text("SELECT count(*) FROM orchestration_tasks WHERE status='RUNNING' AND lease_expires_at <= clock_timestamp()")).scalar_one(),
            case_states=[dict(row) for row in connection.execute(text("SELECT status,count(*) AS count FROM cases GROUP BY status ORDER BY status")).mappings()],
            action_states=[dict(row) for row in connection.execute(text("SELECT status,count(*) AS count FROM actions GROUP BY status ORDER BY status")).mappings()],
            verifications=[dict(row) for row in connection.execute(text("SELECT success,count(*) AS count FROM verification_results GROUP BY success")).mappings()])
        transaction.rollback()
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output")
    args=parser.parse_args()
    engine=create_engine(Settings().database_url)
    try:result=collect(engine)
    finally:engine.dispose()
    content=json.dumps(result,indent=2,default=str)+"\n"
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding="utf-8")
    else:print(content)


if __name__=="__main__":main()
