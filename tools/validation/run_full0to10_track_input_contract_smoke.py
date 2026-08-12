#!/usr/bin/env python3
"""Smoke test for Full0To10 track input contract."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_track_input_contract_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    samples = {
        "demo_analysis.json": {"kind": "analysis"},
        "demo_music_context.json": {"kind": "music_context"},
        "demo_blender_keyframes.json": {"kind": "blender_keyframes"},
    }
    for name, payload in samples.items():
        (input_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    output = work_dir / "contract.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_track_input_contract.py"),
        "--repo-root",
        str(work_dir),
        "--output-dir",
        str(work_dir / "contract"),
        "--track-name",
        "demo",
        "--require-inputs",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    data = json.loads(output.read_text(encoding="utf-8"))
    summary = {
        "passed": proc.returncode == 0 and data["passed"] and data["complete"],
        "missing_roles": data["missing_roles"],
        "outputs": data.get("outputs", {}),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
