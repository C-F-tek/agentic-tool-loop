#!/usr/bin/env python3
"""Smoke test for SQLite embedding cache and hybrid search."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], repo_root: Path) -> None:
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_sqlite_embedding_hybrid_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    db = work_dir / "memory.sqlite"
    cli = repo_root / "Tools/ai/full0to10_memory_tool.py"
    output = work_dir / "hybrid_search.json"

    run([sys.executable, str(cli), "init", "--db", str(db)], repo_root)
    run([sys.executable, str(cli), "add-text", "--db", str(db), "--namespace", "smoke", "--text", "GPU Ollama NPU provider telemetry bundle"], repo_root)
    run([sys.executable, str(cli), "add-text", "--db", str(db), "--namespace", "smoke", "--text", "SQLite FTS5 namespace embedding cache hybrid search"], repo_root)
    run([sys.executable, str(cli), "embed-missing", "--db", str(db), "--namespace", "smoke", "--embedding-provider", "hash", "--limit", "20"], repo_root)
    run([
        sys.executable, str(cli), "search", "--db", str(db), "--namespace", "smoke",
        "--query", "embedding hybrid cache", "--mode", "hybrid",
        "--embedding-provider", "hash", "--output", str(output),
    ], repo_root)

    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({
        "passed": data["passed"],
        "result_count": data["result_count"],
        "cache_hits": data["embedding_cache_hits"],
        "cache_misses": data["embedding_cache_misses"],
    }, indent=2))
    return 0 if data["result_count"] >= 1 and data["embedding_cache_used"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
