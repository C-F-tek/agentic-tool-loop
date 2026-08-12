#!/usr/bin/env python3
"""Smoke test for Full0To10 provider governor."""
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
    parser.add_argument("--work-dir", default="output/validation/full0to10_provider_governor_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    output = work_dir / "governor.json"

    base_cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_provider_governor.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--request",
        "Smoke provider governor GPU permit NPU audit GPU0 guardrail.",
        "--operator-intent",
        "--no-external-probes",
        "--output",
        str(output),
    ]
    proc = run(base_cmd, repo_root)
    data = json.loads(output.read_text(encoding="utf-8"))

    strict_output = work_dir / "governor_strict.json"
    strict_cmd = [*base_cmd[:-1], str(strict_output), "--strict-permit"]
    strict_proc = run(strict_cmd, repo_root)

    permit = work_dir / "full0to10_provider_run_permit.json"
    md = work_dir / "full0to10_provider_governor.md"
    summary = {
        "passed": proc.returncode == 0 and data["passed"] and permit.exists() and md.exists() and strict_proc.returncode == 1,
        "normal_returncode": proc.returncode,
        "strict_returncode": strict_proc.returncode,
        "permit_allowed": data["run_permit"]["permit_allowed"],
        "provider_execution_performed": data["provider_execution_performed"],
        "telemetry_events": data["telemetry"]["event_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] and not summary["provider_execution_performed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
