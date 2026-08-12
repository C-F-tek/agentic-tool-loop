#!/usr/bin/env python3
"""Offline smoke test for Full0To10 hardware/tool capability manifest."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_hardware_tool_capability_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = (repo_root / args.work_dir).resolve()
    output = work_dir / "full0to10_hardware_tool_capability.json"
    markdown = work_dir / "full0to10_hardware_tool_capability.md"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_hardware_tool_capability.py"),
        "--repo-root",
        str(repo_root),
        "--no-external-probes",
        "--output",
        str(output),
        "--markdown-output",
        str(markdown),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({"passed": data["passed"], "missing": data["tool_inventory"]["missing"]}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
