"""Package tracked source, reviewed evidence and local history; preserve frozen worktree bytes."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    root=Path.cwd().resolve()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root.parent/"ResolveOS-hardened-backend.zip")
    args=parser.parse_args()
    target=args.output.resolve()
    bundle=target.with_name(target.stem+"-history.bundle")
    receipt=target.with_name(target.stem+"-package-receipt.json")
    subprocess.run(["git","bundle","create",str(bundle),"HEAD"],check=True)
    output=subprocess.check_output(["git","ls-files","-z"])
    names=[name for name in output.decode().split("\0") if name]
    # Include the complete reviewed local live-AI deliverable before a commit.
    names.extend(["run_live_ai_test.py", "Run-LiveAITest.ps1", "tests/test_live_ai_runner.py", "tests/test_http_status_grounding.py", "tests/test_phase17_live_scenarios.py", "tests/fixtures/live_ai_incomplete_outputs.json"])
    names.extend(["tests/test_completion_semantics.py", "tests/fixtures/scenario_b_live_completion_gap.json"])
    names.append("tests/test_phase18_lifecycle.py")
    names.append("tests/test_temporal_lifecycle.py")
    names.append("tests/test_technology_scope_audit.py")
    names.append("tests/test_phase19_benchmark.py")
    names.append("tests/test_phase20_quality.py")
    for directory in ("app/evaluation", "scripts", "docs/evaluation/phase19", "docs/evaluation/phase20"):
        names.extend(str(path.relative_to(root)).replace("\\", "/") for path in (root/directory).rglob("*") if path.is_file())
    names.extend(str(path.relative_to(root)).replace("\\","/") for path in (root/"docs/live-ai").rglob("*") if path.is_file())
    # Reviewed logs are ignored globally but requested as fresh machine evidence.
    names.extend(str(path.relative_to(root)).replace("\\","/") for path in (root/"docs/hardening/artifacts").glob("*.log"))
    names.append("ResolveOS-phase16.bundle")
    forbidden={".git","node_modules",".next",".tools",".venv","__pycache__"}
    names=sorted(set(names))
    manifest={}
    for name in names:
        path=root/name
        if not path.is_file() or forbidden.intersection(path.parts):continue
        if path.name.startswith(".env") and path.name!=".env.example":continue
        if path.suffix.lower() in {".key",".pem",".pfx",".p12",".pyc",".zip"}:continue
        manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    required={"app/execution/service.py","run_headless_demo.py","run_operational_benchmark.py",
        "docs/hardening/FINAL_ACCEPTANCE_REPORT.md","docs/hardening/FINAL_GAP_REGISTER.md","frontend/package.json",
        "app/evaluation/benchmark.py","app/evaluation/benchmark_manifest.py","app/evaluation/benchmark_scoring.py",
        "app/evaluation/fixture_providers.py","app/evaluation/pilot.py","scripts/run_evaluation_benchmark.py",
        "tests/test_phase19_benchmark.py","docs/evaluation/phase19/PHASE19_ACCEPTANCE_REPORT.md",
        "app/evaluation/quality.py","app/evaluation/experiment.py","scripts/evaluate_quality.py",
        "tests/test_phase20_quality.py","docs/evaluation/phase20/PHASE20_ACCEPTANCE_REPORT.md"}
    if not required.issubset(manifest):raise RuntimeError("required_deliverable_missing")
    frontend=json.loads((root/"docs/hardening/artifacts/frontend-baseline-hashes.json").read_text())
    if any(manifest.get(name)!=expected for name,expected in frontend.items()):raise RuntimeError("frozen_frontend_changed_or_omitted")
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in manifest:archive.write(root/name,"ResolveOS/"+name)
        archive.write(bundle,"ResolveOS/ResolveOS-hardening.bundle")
        archive.writestr("ResolveOS/PACKAGE_MANIFEST.json",json.dumps(manifest,indent=2)+"\n")
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise RuntimeError("zip_integrity_failed")
        for name,expected in manifest.items():
            if hashlib.sha256(archive.read("ResolveOS/"+name)).hexdigest()!=expected:raise RuntimeError("archive_hash_mismatch")
    report=dict(archive=str(target),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        source_and_artifact_files=len(manifest),frontend_files_preserved=len(frontend),zip_crc_and_all_file_hashes_verified=True,
        git_head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        history_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        exclusions=["environment secrets", "virtual environments", "dependency/build caches", "database dumps"],
        preexisting_frontend_difference_preserved="frontend/next-env.d.ts",remote_push=False)
    references=json.loads((root/"docs/hardening/artifacts/source-reference.json").read_text())
    original=root.parent.parent/"ResolveOS-phases1-16-playable.zip"
    expected=next(row["sha256"] for row in references["references"] if row["name"]==original.name)
    report["original_source_zip_unchanged"]=hashlib.sha256(original.read_bytes()).hexdigest()==expected
    if not report["original_source_zip_unchanged"]:raise RuntimeError("original_reference_zip_changed")
    receipt.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
