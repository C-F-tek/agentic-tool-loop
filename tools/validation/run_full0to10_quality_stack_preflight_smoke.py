#!/usr/bin/env python3
"""Smoke test for Full0To10 quality stack preflight."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_quality_stack_preflight_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    specs = work_dir / "patch_specs.json"
    specs.parent.mkdir(parents=True, exist_ok=True)
    specs.write_text(json.dumps([
        {"candidate_kind": "markdown_split", "target_path": "docs/example.md"},
        {"candidate_kind": "gpu_telemetry_visibility", "target_path": "Tools/ai/gpu.py"},
    ], indent=2), encoding="utf-8")

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "Tools/workflow/run_full0to10_quality_stack_preflight.ps1"),
        "-RepoRoot",
        str(repo_root),
        "-OutputDir",
        str(work_dir),
        "-PatchSpecs",
        str(specs),
        "-NoExternalProbes",
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    summary = json.loads((work_dir / "full0to10_quality_stack_preflight.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "passed": summary["passed"],
        "score": summary["readiness"]["score"],
        "ready_for_real_run": summary["readiness"]["ready_for_real_run"],
    }, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
