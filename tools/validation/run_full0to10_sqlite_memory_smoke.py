#!/usr/bin/env python3
"""Smoke test for Full0To10 SQLite memory core."""
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
    parser.add_argument("--work-dir", default="output/validation/full0to10_sqlite_memory_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    sample = work_dir / "sample.md"
    sample.write_text("# Memory\nSQLite FTS5 namespace hybrid search bundle evidence.\n", encoding="utf-8")
    db = work_dir / "memory.sqlite"
    cli = repo_root / "Tools/ai/full0to10_memory_tool.py"

    run([sys.executable, str(cli), "init", "--db", str(db)], repo_root)
    run([sys.executable, str(cli), "add-text", "--db", str(db), "--namespace", "smoke", "--text", "Ollama GPU NPU toolbox memory"], repo_root)
    run([sys.executable, str(cli), "add-file", "--db", str(db), "--namespace", "smoke", "--path", str(sample)], repo_root)
    output = work_dir / "search.json"
    run([sys.executable, str(cli), "search", "--db", str(db), "--namespace", "smoke", "--query", "SQLite", "--output", str(output)], repo_root)
    data = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({"passed": data["passed"], "result_count": data["result_count"]}, indent=2))
    return 0 if data["result_count"] >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
