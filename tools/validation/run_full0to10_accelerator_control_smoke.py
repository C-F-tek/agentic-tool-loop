#!/usr/bin/env python3
"""Smoke test for Full0To10 accelerator control plane."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_accelerator_control_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    output = work_dir / "control.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_accelerator_control.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--request",
        "Smoke accelerator control for GPU body mind NPU auditor GPU0.",
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
    md = work_dir / "full0to10_accelerator_control.md"
    telemetry = work_dir / "full0to10_accelerator_telemetry.json"
    summary = {
        "passed": data["passed"] and md.exists() and telemetry.exists(),
        "scheduler_generation_allowed": data["scheduler"]["generation_allowed"],
        "gpu_mind_may_generate": data["gpu_mind"]["decision_policy"]["may_generate"],
        "telemetry_exists": telemetry.exists(),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] and not summary["scheduler_generation_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
