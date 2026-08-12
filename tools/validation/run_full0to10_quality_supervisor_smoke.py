#!/usr/bin/env python3
"""Smoke test for Full0To10 quality supervisor integration."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_quality_supervisor_smoke")
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
        str(repo_root / "Tools/workflow/run_unified_full0to10_quality_supervisor.ps1"),
        "-RepoRoot",
        str(repo_root),
        "-OutputDir",
        str(work_dir / "supervisor"),
        "-PatchSpecs",
        str(specs),
        "-SkipLauncher",
        "-NoExternalProbes",
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    preflight = work_dir / "supervisor" / "preflight" / "full0to10_quality_stack_preflight.json"
    final = work_dir / "supervisor" / "final" / "full0to10_quality_stack_preflight.json"
    summary = {
        "passed": proc.returncode == 0 and preflight.exists() and final.exists(),
        "preflight_exists": preflight.exists(),
        "final_exists": final.exists(),
        "returncode": proc.returncode,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
