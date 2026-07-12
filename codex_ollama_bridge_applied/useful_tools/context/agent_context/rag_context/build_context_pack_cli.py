"""Build a heap-consumable RAG context pack artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    DEFAULT_CHAR_BUDGET,
    DEFAULT_DB,
    DEFAULT_EMBEDDING_ENDPOINT,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TOP_K,
    resolve_repo_path,
    write_json,
)
from .context_pack import build_context_pack, render_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--query", default="")
    parser.add_argument("--task-file", default="")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--char-budget", type=int, default=DEFAULT_CHAR_BUDGET)
    parser.add_argument("--embedding-endpoint", default=DEFAULT_EMBEDDING_ENDPOINT)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--skip-query-embedding", action="store_true")
    parser.add_argument("--allow-missing-query-embedding", action="store_true")
    parser.add_argument("--allow-empty-results", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    pack = build_context_pack(
        repo_root=repo_root,
        db_path=resolve_repo_path(repo_root, args.db),
        query=args.query,
        task_file=args.task_file,
        top_k=args.top_k,
        char_budget=args.char_budget,
        embedding_endpoint=args.embedding_endpoint,
        embedding_model=args.embedding_model,
        query_embedding=not args.skip_query_embedding,
        require_query_embedding=not args.skip_query_embedding
        and not args.allow_missing_query_embedding,
        require_results=not args.allow_empty_results,
    )
    output = resolve_repo_path(repo_root, args.output)
    markdown = resolve_repo_path(repo_root, args.markdown_output)
    write_json(output, pack)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(pack), encoding="utf-8")
    print(json.dumps(pack, indent=2, ensure_ascii=False))
    return 0 if pack["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
