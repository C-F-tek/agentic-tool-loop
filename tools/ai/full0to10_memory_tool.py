#!/usr/bin/env python3
"""Full0To10 SQLite memory CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_sqlite_memory.db import connect  # noqa: E402
from full0to10_sqlite_memory.embedding import embed_missing_chunks  # noqa: E402
from full0to10_sqlite_memory.ingest import memory_add_file, memory_add_text  # noqa: E402
from full0to10_sqlite_memory.manifest import build_memory_manifest  # noqa: E402
from full0to10_sqlite_memory.render import render_markdown  # noqa: E402
from full0to10_sqlite_memory.schema import init_schema  # noqa: E402
from full0to10_sqlite_memory.search import memory_search  # noqa: E402


def write_report(report: dict[str, object], output: str | None, markdown_output: str | None) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text)
    if markdown_output:
        md = Path(markdown_output)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "add-text", "add-file", "search", "manifest", "embed-missing"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--text")
    parser.add_argument("--title")
    parser.add_argument("--path")
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mode", default="hybrid", choices=("fts", "hybrid"))
    parser.add_argument("--embedding-provider", default="none", choices=("none", "hash", "ollama"))
    parser.add_argument("--embedding-model", default="hash-local-v1")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output")
    parser.add_argument("--markdown-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    conn = connect(db_path)
    if args.command == "init":
        init_schema(conn)
        report = {"kind": "memory_init", "passed": True, "db": str(db_path)}
    elif args.command == "add-text":
        if not args.text:
            raise SystemExit("--text is required")
        report = memory_add_text(conn, args.namespace, args.text, title=args.title)
    elif args.command == "add-file":
        if not args.path:
            raise SystemExit("--path is required")
        report = memory_add_file(conn, args.namespace, Path(args.path))
    elif args.command == "search":
        if not args.query:
            raise SystemExit("--query is required")
        report = memory_search(
            conn,
            args.namespace,
            args.query,
            limit=args.limit,
            mode=args.mode,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            ollama_url=args.ollama_url,
        )
    elif args.command == "embed-missing":
        report = embed_missing_chunks(
            conn,
            args.namespace,
            args.embedding_model,
            args.embedding_provider if args.embedding_provider != "none" else "hash",
            args.ollama_url,
            args.limit,
        )
    else:
        report = build_memory_manifest(conn, db_path)
    write_report(report, args.output, args.markdown_output)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
