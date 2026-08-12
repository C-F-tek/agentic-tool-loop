#!/usr/bin/env python3
"""Smoke test for Full0To10 provider invocation dry-run plan."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_provider_invocation_plan_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    output = work_dir / "plan.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_provider_invocation_plan.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--request",
        "Smoke provider invocation dry-run plan.",
        "--operator-intent",
        "--no-external-probes",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    data = json.loads(output.read_text(encoding="utf-8"))
    md = work_dir / "full0to10_provider_invocation_plan.md"
    workload = work_dir / "full0to10_provider_workload_report_contract.json"
    telemetry = work_dir / "full0to10_provider_expected_telemetry_contract.json"
    summary = {
        "passed": proc.returncode == 0 and data["passed"] and md.exists() and workload.exists() and telemetry.exists(),
        "generation_executes_now": data["generation_executes_now"],
        "ready_for_bundle_inclusion": data["readiness"]["ready_for_bundle_inclusion"],
        "permit_decision": data["permit_decision"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] and not summary["generation_executes_now"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
