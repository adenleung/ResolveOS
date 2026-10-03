"""Explicit worker process: python -m app.orchestration.worker --once.

The local CLI has database credentials and must run only as a trusted operator.
"""
import argparse
import socket
import time
from uuid import uuid4

from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.database import DatabaseManager
from app.orchestration.queue import LeaseLost, WorkQueue
from app.orchestration.service import OrchestrationService


def run_once(database, owner, settings, *, poll=False, after_case_id=None, provider=None, supervisor_provider=None,
             memory_access_provider=None):
    from app.investigation.contracts import HANDLERS
    from app.investigation.provider import OpenAIProvider
    from app.investigation.service import InvestigationRunner
    from app.investigation.contracts import SupervisorOutput
    from app.supervisor.service import SupervisorRunner, SUPERVISOR_TASK
    from app.execution.service import ExecutionEngine, EXECUTION_HANDLERS
    if provider is None and settings.investigator_live_enabled:
        provider = OpenAIProvider(settings)
    if supervisor_provider is None and settings.investigator_live_enabled:
        supervisor_provider = OpenAIProvider(settings, output_model=SupervisorOutput)
    runner = InvestigationRunner(database, settings, provider, memory_access_provider) if provider is not None else None
    supervisor = SupervisorRunner(database, settings, supervisor_provider) if supervisor_provider is not None else None
    with database.get_session() as session:
        service = OrchestrationService(session, settings)
        maintenance = service.maintenance()
        page = service.poll_cases(after_case_id) if poll else None
        if runner:
            runner.activate(session)
        if supervisor:
            supervisor.activate(session)
        service.queue = WorkQueue(session, settings, handlers=(HANDLERS if runner else set()) |
            ({SUPERVISOR_TASK} if supervisor else set()) | EXECUTION_HANDLERS)
        tasks = service.queue.claim(owner, limit=1)
        session.commit()
    for claimed in tasks:
        try:
            if claimed["task_type"] in EXECUTION_HANDLERS:
                with database.get_session() as session:
                    ExecutionEngine(session, settings).execute(claimed["id"], owner, claimed["lease_token"])
                continue
            if claimed["task_type"] == SUPERVISOR_TASK:
                supervisor.run(claimed["id"], owner, claimed["lease_token"])
                continue
            if claimed["task_type"] in HANDLERS:
                runner.run(claimed["id"], owner, claimed["lease_token"])
                continue
            with database.get_session() as session:
                OrchestrationService(session, settings).execute(claimed["id"], owner, claimed["lease_token"])
        except LeaseLost:
            pass  # Another worker owns recovery; stale effects have rolled back.
        except Exception as exc:
            # Store safe error codes, not exception strings containing SQL/source data.
            with database.get_session() as session:
                try:
                    WorkQueue(session, settings).fail(claimed["id"], owner, claimed["lease_token"],
                        type(exc).__name__, transient=isinstance(exc, (DBAPIError, TimeoutError, ConnectionError)))
                    session.commit()
                except LeaseLost:
                    session.rollback()
    with database.get_session() as session:
        ExecutionEngine(session, settings).reconcile_terminal()
    return {**maintenance, "claimed": len(tasks), "next_after_case_id": page["next_after_case_id"] if page else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", action="store_true", help="Discover eligible cases in bounded pages")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    settings = get_settings()
    database = DatabaseManager(settings.database_url)
    owner = f"{socket.gethostname()}-{uuid4().hex[:12]}"
    cursor = None
    try:
        while True:
            result = run_once(database, owner, settings, poll=args.poll, after_case_id=cursor)
            cursor = result["next_after_case_id"]
            if args.once:
                print(result)
                break
            time.sleep(max(0.1, min(args.interval, 60)))
    except KeyboardInterrupt:
        pass
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
