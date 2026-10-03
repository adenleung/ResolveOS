"""Start one local service with ignored demo credentials; no secrets printed."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["backend", "worker", "frontend"])
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    local = dotenv_values(root / ".env.demo")
    if not local.get("DATABASE_URL"): raise SystemExit("Run python -m app.demo --create first")
    url = make_url(local["DATABASE_URL"])
    assert re.fullmatch(r"resolveos_demo_[0-9a-f]{10}", url.database)
    assert url.host in {"localhost", "127.0.0.1"} and url.port == 5433
    for key, value in local.items():
        if value is not None: os.environ[key] = value
    os.environ["INVESTIGATOR_LIVE_ENABLED"] = "false"
    if args.service == "backend":
        return subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=root)
    if args.service == "frontend":
        node = shutil.which("node")
        portable = sorted((root / ".tools").glob("node-v*-win-x64/node.exe"))
        if node is None and portable: node = str(portable[-1])
        if node is None: raise SystemExit("Node.js LTS is required")
        return subprocess.call([node, str(root / "frontend/node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1"], cwd=root / "frontend")
    from app.config import get_settings
    from app.database import DatabaseManager
    from app.demo import ObservedDemoSpecialist, ObservedDemoSupervisor
    from app.orchestration.worker import run_once
    settings = get_settings()
    database = DatabaseManager(settings.database_url)
    try:
        while True:
            result = run_once(database, "explicit-isolated-demo-worker", settings, poll=True,
                provider=ObservedDemoSpecialist(), supervisor_provider=ObservedDemoSupervisor())
            if args.once: return 0
            time.sleep(1)
    except KeyboardInterrupt: return 0


if __name__ == "__main__": raise SystemExit(main())
