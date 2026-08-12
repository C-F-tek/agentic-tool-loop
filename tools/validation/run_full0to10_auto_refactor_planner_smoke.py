#!/usr/bin/env python3
"""Smoke test for Full0To10 auto-refactor hardware planner."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_auto_refactor_planner_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    sample_root = work_dir / "sample"
    sample_root.mkdir(parents=True, exist_ok=True)
    (sample_root / "large.md").write_text("# Title\n" + ("line\n" * 510), encoding="utf-8")
    (sample_root / "gpu_npu.py").write_text("GPU=True\n# openvino npu device\n", encoding="utf-8")

    output = work_dir / "plan.json"
    markdown = work_dir / "plan.md"
    specs = work_dir / "patch_specs.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_auto_refactor_plan.py"),
        "--repo-root",
        str(work_dir),
        "--scan-root",
        "sample",
        "--output",
        str(output),
        "--markdown-output",
        str(markdown),
        "--patch-specs-output",
        str(specs),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        return proc.returncode

    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({
        "passed": data["passed"],
        "candidate_count": data["candidate_count"],
        "hardware_candidate_count": data["hardware_candidate_count"],
    }, indent=2))
    return 0 if data["candidate_count"] >= 2 and data["hardware_candidate_count"] >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
