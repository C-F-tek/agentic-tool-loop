#!/usr/bin/env python3
"""Smoke test for Full0To10 repo quality packet."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_repo_quality_packet_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    sample_dir = work_dir / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "README.md").write_text("# Full0To10\n\nQuality provider GPU NPU SQLite.\n", encoding="utf-8")
    (sample_dir / "tool.py").write_text("import argparse\n\ndef main():\n    return 0\n", encoding="utf-8")

    output = work_dir / "packet.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_repo_quality_packet.py"),
        "--repo-root",
        str(work_dir),
        "--output-dir",
        str(work_dir / "packet"),
        "--input",
        str(sample_dir),
        "--output-file",
        str(work_dir / "packet" / "quality.md"),
        "--write-output",
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
        "passed": proc.returncode == 0 and data["passed"] and data["inventory"]["file_count"] >= 2,
        "file_count": data["inventory"]["file_count"],
        "routes": data["tool_plan"]["routes"],
        "user_output_written": data["user_output"]["written"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
