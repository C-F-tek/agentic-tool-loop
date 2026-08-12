#!/usr/bin/env python3
"""Smoke test for Full0To10 runtime memory tool registry."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], repo_root: Path) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        print(proc.stdout)
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_runtime_memory_tool_registry_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    db = work_dir / "runtime_memory.sqlite"
    cli = repo_root / "Tools/ai/full0to10_runtime_tool.py"

    registry = run([sys.executable, str(cli), "list", "--repo-root", str(repo_root)], repo_root)
    init = run([sys.executable, str(cli), "memory_init", "--args-json", json.dumps({"db": str(db)})], repo_root)
    add = run([
        sys.executable, str(cli), "memory_add_text", "--args-json",
        json.dumps({"db": str(db), "namespace": "smoke", "text": "CarmineLike Full0To10 runtime memory tool"}),
    ], repo_root)
    search = run([
        sys.executable, str(cli), "memory_search", "--args-json",
        json.dumps({"db": str(db), "namespace": "smoke", "query": "runtime memory", "mode": "fts"}),
    ], repo_root)

    summary = {
        "passed": registry["passed"] and init["passed"] and add["passed"] and search["result_count"] >= 1,
        "tool_count": registry["tool_count"],
        "search_results": search["result_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
