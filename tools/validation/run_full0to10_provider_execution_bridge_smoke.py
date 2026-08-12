#!/usr/bin/env python3
"""Smoke test for Full0To10 provider execution bridge."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_provider_execution_bridge_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    output = work_dir / "bridge.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_provider_execution_bridge.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--request",
        "Smoke provider execution bridge.",
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
    md = work_dir / "full0to10_provider_execution_bridge.md"
    gate = work_dir / "full0to10_provider_real_run_gate.json"
    command = work_dir / "full0to10_provider_command_plan.json"
    summary = {
        "passed": proc.returncode == 0 and data["passed"] and md.exists() and gate.exists() and command.exists(),
        "real_run_allowed": data["real_run_gate"]["real_run_allowed"],
        "provider_execution_performed": data["provider_execution_performed"],
        "all_commands_non_executing": data["command_plan"]["all_commands_are_non_executing"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] and not summary["provider_execution_performed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
