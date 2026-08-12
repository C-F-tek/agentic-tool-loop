#!/usr/bin/env python3
"""Smoke test for AI workload quality --report-dir semantics."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


GOOD_REPORT = """# Workload report

This provider workload report contains human-readable advisory evidence. It
describes GPU, NPU, telemetry, routing, decision quality, and expected usage in
the Full0To10 workflow. The content is long enough and textual enough for the
quality gate to classify it as useful. It is report-only and does not execute
providers.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/ai_workload_quality_report_dir_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    packet = work_dir / "packets" / "20260505-000000"
    packet.mkdir(parents=True, exist_ok=True)
    (packet / "ollama_gpu_real_workload_report.md").write_text(GOOD_REPORT, encoding="utf-8")
    (packet / "npu_real_workload_report.md").write_text(GOOD_REPORT, encoding="utf-8")

    output = work_dir / "quality.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/validation/check_ai_workload_report_quality.py"),
        "--repo-root",
        str(repo_root),
        "--report-dir",
        str(work_dir / "packets"),
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
        "passed": data["passed"],
        "report_count": data["checks"]["report_count"],
        "usable_lanes": data["usable_lanes"],
        "report_dir_cli_supported": data["report_dir_cli_supported"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if data["passed"] and data["checks"]["report_count"] >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
