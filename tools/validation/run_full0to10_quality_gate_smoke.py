#!/usr/bin/env python3
"""Smoke test for Full0To10 quality gate."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_quality_gate_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    specs = work_dir / "patch_specs.json"
    specs.write_text(json.dumps([
        {"candidate_kind": "markdown_split", "target_path": "docs/example.md"},
        {"candidate_kind": "code_split_candidate", "target_path": "Tools/example.py"},
        {"candidate_kind": "gpu_telemetry_visibility", "target_path": "Tools/ai/gpu.py"},
    ], indent=2), encoding="utf-8")
    output = work_dir / "quality.json"
    md = work_dir / "quality.md"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_quality_gate.py"),
        "--repo-root",
        str(repo_root),
        "--patch-specs",
        str(specs),
        "--output",
        str(output),
        "--markdown-output",
        str(md),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({
        "passed": data["passed"],
        "score": data["readiness"]["score"],
        "split_specs": data["split_advisory"]["spec_count"],
    }, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
