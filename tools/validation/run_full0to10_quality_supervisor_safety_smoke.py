#!/usr/bin/env python3
"""Smoke test for quality supervisor safe default and --report-dir compatibility."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_quality_supervisor_safety_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    reports = work_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "sample.json").write_text(json.dumps({"kind": "sample", "passed": True}, indent=2), encoding="utf-8")

    quality_output = work_dir / "ai_workload_quality.json"
    proc_quality = run([
        sys.executable,
        str(repo_root / "Tools/validation/check_ai_workload_report_quality.py"),
        "--repo-root",
        str(repo_root),
        "--report-dir",
        str(reports),
        "--output",
        str(quality_output),
    ], repo_root)

    proc_supervisor = run([
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "Tools/workflow/run_unified_full0to10_quality_supervisor.ps1"),
        "-RepoRoot",
        str(repo_root),
        "-OutputDir",
        str(work_dir / "supervisor"),
        "-NoExternalProbes",
    ], repo_root)

    supervisor_log = (proc_supervisor.stdout or "") + (proc_supervisor.stderr or "")
    summary = {
        "passed": proc_quality.returncode == 0 and proc_supervisor.returncode == 0 and "Quality-only mode" in supervisor_log,
        "report_dir_compatible": proc_quality.returncode == 0,
        "safe_default_quality_only": "Quality-only mode" in supervisor_log,
        "supervisor_returncode": proc_supervisor.returncode,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
