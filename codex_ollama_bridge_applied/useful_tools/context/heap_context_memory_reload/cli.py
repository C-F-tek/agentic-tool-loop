"""CLI for heap startup context and memory reload."""

from __future__ import annotations

import argparse
from pathlib import Path

from ia_carmine.context.heap_context_memory_reload.common import (
    now_stamp,
    read_request_file,
    resolve_project_python,
)
from ia_carmine.context.heap_context_memory_reload.runner import run_reload
from ia_carmine.context.heap_context_memory_reload.runner_state import ReloadRun


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--request", default="")
    parser.add_argument(
        "--request-file",
        default="",
        help="Read startup request text from file to avoid long Windows command lines.",
    )
    parser.add_argument("--stamp", default="")
    parser.add_argument("--python-exe", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-memory-chars", type=int, default=None)
    parser.add_argument("--max-context-files", type=int, default=None)
    parser.add_argument("--startup-scan-context-files", type=int, default=None)
    parser.add_argument("--max-chars-per-file", type=int, default=None)
    parser.add_argument("--rag-db", default="")
    parser.add_argument("--rag-index-policy", choices=("auto", "always", "never"), default="")
    parser.add_argument("--rag-top-k", type=int, default=None)
    parser.add_argument("--rag-char-budget", type=int, default=None)
    parser.add_argument("--rag-embedding-endpoint", default="")
    parser.add_argument("--rag-embedding-model", default="")
    parser.add_argument("--rag-ingest-batch-size", type=int, default=None)
    parser.add_argument("--rag-embed-smoke-batch-size", type=int, default=None)
    parser.add_argument("--rag-chunk-min-chars", type=int, default=None)
    parser.add_argument("--rag-chunk-max-chars", type=int, default=None)
    parser.add_argument("--rag-chunk-overlap-chars", type=int, default=None)
    parser.add_argument("--rag-max-file-size", type=int, default=None)
    parser.add_argument("--rag-allow-missing-embeddings", action="store_true")
    parser.add_argument("--rag-skip-query-embedding", action="store_true")
    parser.add_argument("--startup-provider-input-workers", type=int, default=None)
    parser.add_argument("--startup-required-context-profile", default="")
    parser.add_argument("--ai-context-pack-profile", default="")
    parser.add_argument(
        "--startup-operational-memory-query",
        default="",
    )
    parser.add_argument("--startup-operational-memory-limit", type=int, default=None)
    parser.add_argument(
        "--strict-ai-context-pack",
        action="store_true",
        help="Compatibility flag; AI context pack is always startup-blocking.",
    )
    parser.add_argument(
        "--strict-startup-reload",
        action="store_true",
        help="Compatibility flag; startup reload degradation is always blocking.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    request_text = (
        read_request_file(repo_root, args.request_file)
        if args.request_file
        else (args.request or "")
    )
    state = ReloadRun(
        args=args,
        repo_root=repo_root,
        stamp=args.stamp or now_stamp(),
        project_python=resolve_project_python(repo_root, args.python_exe),
        output_dir=Path(args.output_dir).resolve(),
        request_text=request_text,
    )
    return run_reload(state)
