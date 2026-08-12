#!/usr/bin/env python3
"""Smoke test for Full0To10 effective use optimization."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_effective_use_optimization_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    output = work_dir / "summary.json"
    db = work_dir / "effective_use.sqlite"
    request = "Smoke: produce quality product from SQLite FTS5 tool request for GPU NPU Ollama readiness."
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_effective_use_optimization.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--db",
        str(db),
        "--request",
        request,
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
    product = work_dir / "full0to10_effective_use_quality_product.md"
    summary = {
        "passed": data["passed"] and product.exists(),
        "quality_product_exists": product.exists(),
        "tool_events": data["tool_telemetry"]["event_count"],
        "memory_chunks": data["memory_report"]["manifest"]["chunk_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] and summary["tool_events"] >= 4 and summary["memory_chunks"] >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
