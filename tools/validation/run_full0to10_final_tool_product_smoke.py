#!/usr/bin/env python3
"""Smoke test for Full0To10 final tool product package."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_final_tool_product_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    output = work_dir / "manifest.json"
    cmd = [
        sys.executable,
        str(repo_root / "Tools/ai/build_full0to10_final_tool_product.py"),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(work_dir),
        "--request",
        "Smoke final product package for SQLite FTS5 GPU NPU tool readiness.",
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
    product = work_dir / "full0to10_final_tool_product.md"
    evidence = work_dir / "full0to10_final_tool_product_evidence_index.json"
    readiness = work_dir / "full0to10_final_tool_product_readiness.json"
    summary = {
        "passed": data["passed"] and product.exists() and evidence.exists() and readiness.exists(),
        "product_exists": product.exists(),
        "evidence_exists": evidence.exists(),
        "readiness_exists": readiness.exists(),
        "ready_for_review": data["readiness"]["ready_for_tool_product_review"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
