"""Fresh HTTP process/worker startup and read-only diagnostics on owned PostgreSQL."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from app.evaluation.database import disposable_database
from run_backend_diagnostics import collect


def main():
    with disposable_database() as (database,settings):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port)],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError("backend_process_exited")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/ready",timeout=1) as response:
                        ready=dict(status=response.status,body=json.loads(response.read()));break
                except OSError:time.sleep(.1)
            else:raise RuntimeError("backend_startup_timeout")
            with urlopen(f"http://127.0.0.1:{port}/health",timeout=2) as response:
                health=dict(status=response.status,body=json.loads(response.read()))
            worker=subprocess.run([sys.executable,"-m","app.orchestration.worker","--once","--poll"],capture_output=True,text=True,timeout=30)
            assert worker.returncode==0
            diagnostics=collect(database.engine)
            report=dict(ready=ready,health=health,worker_exit_code=worker.returncode,diagnostics=diagnostics,
                scope="Fresh empty migrated database and real processes; source-to-resolution journeys are exported separately")
            Path("docs/hardening/artifacts/runtime-smoke.json").write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
            print("HTTP readiness/health, worker process and read-only diagnostics passed")
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)


if __name__=="__main__":main()
