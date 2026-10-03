"""Reproducible local frontend acceptance with machine-readable command results."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def main():
    root = Path(__file__).resolve().parent
    portable = sorted((root / ".tools").glob("node-v*-win-x64/node.exe"))
    node = shutil.which("node") or (str(portable[-1]) if portable else None)
    if node is None: raise SystemExit("Install Node.js LTS first")
    npm = Path(node).parent / "node_modules/npm/bin/npm-cli.js"
    if not npm.is_file(): raise SystemExit("Node's npm CLI is required")
    environment = os.environ.copy()
    environment["PATH"] = str(Path(node).parent)+os.pathsep+environment.get("PATH", "")
    environment["NEXT_TELEMETRY_DISABLED"] = "1"
    environment["npm_config_cache"] = str(root / ".tools/npm-cache")
    results = {"node_version": subprocess.check_output([node, "--version"], text=True).strip(), "steps": []}
    for task in ("typecheck", "lint", "test", "build"):
        started = time.perf_counter()
        result = subprocess.run([node, str(npm), "run", task], cwd=root / "frontend", env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
        output = result.stdout+result.stderr
        (root / f"phase15-frontend-{task}.log").write_text(output, encoding="utf-8")
        results["steps"].append({"command": "npm run "+task, "exit_code": result.returncode,
            "seconds": round(time.perf_counter()-started, 3), "output_sha256": hashlib.sha256(output.encode()).hexdigest()})
        print(task+": "+("passed" if result.returncode == 0 else "FAILED"))
        if result.returncode:
            print(output)
            (root / "phase15-frontend-validation.json").write_text(json.dumps(results, indent=2)+"\n")
            return result.returncode
    audit = subprocess.run([node, str(npm), "audit", "--json"], cwd=root / "frontend", env=environment, capture_output=True, text=True, encoding="utf-8")
    (root / "phase15-npm-audit.json").write_text(audit.stdout, encoding="utf-8")
    report = json.loads(audit.stdout)
    assert audit.returncode == 0 and report["metadata"]["vulnerabilities"]["total"] == 0
    results["dependency_audit"] = report["metadata"]["vulnerabilities"]
    results["production_build"] = "Next.js production webpack build; no external fonts or telemetry"
    (root / "phase15-frontend-validation.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
    print("Frontend acceptance passed; dependency audit reports zero vulnerabilities.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
