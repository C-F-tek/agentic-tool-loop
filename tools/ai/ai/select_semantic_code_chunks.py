#!/usr/bin/env python3
"""Select focused semantic code chunks for local AI context.

This tool is report-only. It reads the generated semantic chunk index,
selects chunks using deterministic keyword scoring, optionally extracts bounded
source excerpts, and writes JSON/Markdown context bundles.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CHUNKS = "indexAI/code_chunks/semantic_code_chunks.json"
DEFAULT_OUTPUT = "output/ai_context_packs/selected_semantic_code_chunks.json"
DEFAULT_MARKDOWN = "output/ai_context_packs/selected_semantic_code_chunks.md"
TOKEN_RE = re.compile(r"[a-zA-Z0-9_./-]+")


def tokenize(value: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(value or "") if len(item) >= 2]


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def as_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {as_text(item)}" for key, item in value.items())
    return str(value or "")


def chunk_haystack(chunk: dict[str, Any]) -> str:
    fields = [
        chunk.get("chunk_id"),
        chunk.get("path"),
        chunk.get("symbol"),
        chunk.get("kind"),
        chunk.get("summary_short"),
        chunk.get("domain"),
        chunk.get("dependencies"),
        chunk.get("blender_api"),
        chunk.get("risk"),
        chunk.get("risk_signals"),
        chunk.get("compatibility_notes"),
    ]
    return " ".join(as_text(item) for item in fields).lower()


def score_chunk(chunk: dict[str, Any], query_tokens: list[str], path_boosts: list[str]) -> tuple[int, list[str]]:
    hay = chunk_haystack(chunk)
    path = str(chunk.get("path") or "").lower()
    symbol = str(chunk.get("symbol") or "").lower()
    domain = [str(item).lower() for item in chunk.get("domain") or []]
    matched: list[str] = []
    score = 0

    for token in query_tokens:
        if token in hay:
            matched.append(token)
            score += 1
        if token in path:
            score += 3
        if token in symbol:
            score += 2
        if token in domain:
            score += 2

    for boost in path_boosts:
        b = boost.lower().strip().replace("\\", "/")
        if b and b in path:
            matched.append(f"path:{boost}")
            score += 8

    if chunk.get("do_not_change") is True:
        score -= 1
    risk = str(chunk.get("risk") or "").lower()
    if risk == "high":
        score += 1

    return score, sorted(set(matched))


def source_excerpt(repo_root: Path, chunk: dict[str, Any], max_chars: int) -> tuple[str, bool]:
    path = repo_root / str(chunk.get("path") or "")
    if not path.exists() or not path.is_file():
        return "", False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return "", False
    start = max(int(chunk.get("line_start") or 1), 1)
    end = max(int(chunk.get("line_end") or start), start)
    excerpt_lines = lines[start - 1 : min(end, len(lines))]
    excerpt = "\n".join(excerpt_lines)
    if len(excerpt) <= max_chars:
        return excerpt, False
    return excerpt[:max_chars] + "\n...[truncated]", True


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Selected Semantic Code Chunks")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Query: `{payload['query']}`")
    lines.append(f"- Selected chunks: `{payload['selected_count']}`")
    lines.append(f"- Total selected chars: `{payload['total_selected_chars']}`")
    lines.append(f"- Source writes performed: `{payload['source_writes_performed']}`")
    lines.append("")
    for item in payload["selected_chunks"]:
        lines.append(f"## {item['chunk_id']}")
        lines.append("")
        lines.append(f"- Path: `{item['path']}`")
        lines.append(f"- Symbol: `{item['symbol']}`")
        lines.append(f"- Lines: `{item['line_start']}-{item['line_end']}`")
        lines.append(f"- Score: `{item['score']}`")
        lines.append(f"- Domain: `{', '.join(item.get('domain') or [])}`")
        lines.append(f"- Risk: `{item.get('risk')}`")
        lines.append(f"- Do not change: `{item.get('do_not_change')}`")
        if item.get("matched_terms"):
            lines.append(f"- Matched terms: `{', '.join(item['matched_terms'])}`")
        if item.get("summary_short"):
            lines.append(f"- Summary: {item['summary_short']}")
        if item.get("source_excerpt"):
            lang = "python" if str(item.get("path", "")).endswith(".py") else "text"
            lines.append("")
            lines.append(f"```{lang}")
            lines.append(item["source_excerpt"])
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_selection(
    repo_root: Path,
    chunks_path: Path,
    query: str,
    max_chunks: int,
    max_total_chars: int,
    max_excerpt_chars: int,
    path_boosts: list[str],
    include_code: bool,
) -> dict[str, Any]:
    chunk_data = read_json(chunks_path)
    chunks = chunk_data.get("chunks") or []
    if not isinstance(chunks, list):
        raise ValueError("semantic chunks payload must contain a chunks list")
    query_tokens = tokenize(query)
    if not query_tokens and not path_boosts:
        raise ValueError("query or path boost is required")

    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        score, matched = score_chunk(chunk, query_tokens, path_boosts)
        if score <= 0:
            continue
        item = dict(chunk)
        item["score"] = score
        item["matched_terms"] = matched
        scored.append(item)

    scored.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or ""), int(item.get("line_start") or 0)))

    selected: list[dict[str, Any]] = []
    total_chars = 0
    for item in scored:
        if len(selected) >= max_chunks:
            break
        out = {
            "chunk_id": item.get("chunk_id"),
            "path": item.get("path"),
            "symbol": item.get("symbol"),
            "kind": item.get("kind"),
            "line_start": item.get("line_start"),
            "line_end": item.get("line_end"),
            "domain": item.get("domain") or [],
            "risk": item.get("risk"),
            "risk_signals": item.get("risk_signals") or [],
            "compatibility_notes": item.get("compatibility_notes") or [],
            "dependencies": item.get("dependencies") or [],
            "blender_api": item.get("blender_api") or [],
            "summary_short": item.get("summary_short"),
            "do_not_change": bool(item.get("do_not_change")),
            "sha256": item.get("sha256"),
            "score": item.get("score"),
            "matched_terms": item.get("matched_terms") or [],
        }
        excerpt = ""
        truncated = False
        if include_code:
            remaining = max(max_total_chars - total_chars, 0)
            if remaining <= 0:
                break
            excerpt_limit = min(max_excerpt_chars, remaining)
            excerpt, truncated = source_excerpt(repo_root, item, excerpt_limit)
            out["source_excerpt"] = excerpt
            out["source_excerpt_truncated"] = truncated
            total_chars += len(excerpt)
        else:
            total_chars += len(json.dumps(out, ensure_ascii=False))
        selected.append(out)

    return {
        "schema_version": 1,
        "kind": "semantic_code_chunk_selection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "source_chunks": chunks_path.relative_to(repo_root).as_posix() if chunks_path.is_relative_to(repo_root) else str(chunks_path),
        "max_chunks": max_chunks,
        "max_total_chars": max_total_chars,
        "max_excerpt_chars": max_excerpt_chars,
        "include_code": include_code,
        "path_boosts": path_boosts,
        "total_scored_chunks": len(scored),
        "selected_count": len(selected),
        "total_selected_chars": total_chars,
        "source_writes_performed": False,
        "provider_execution_performed": False,
        "passed": True,
        "errors": [],
        "warnings": [] if selected else ["no chunks matched query"],
        "selected_chunks": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--chunks", default=DEFAULT_CHUNKS)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-chunks", type=int, default=20)
    parser.add_argument("--max-total-chars", type=int, default=24000)
    parser.add_argument("--max-excerpt-chars", type=int, default=2500)
    parser.add_argument("--path-boost", action="append", default=[])
    parser.add_argument("--no-code", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = repo_root / chunks_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    markdown_path = Path(args.markdown_output)
    if not markdown_path.is_absolute():
        markdown_path = repo_root / markdown_path

    payload = build_selection(
        repo_root=repo_root,
        chunks_path=chunks_path,
        query=args.query,
        max_chunks=args.max_chunks,
        max_total_chars=args.max_total_chars,
        max_excerpt_chars=args.max_excerpt_chars,
        path_boosts=args.path_boost,
        include_code=not args.no_code,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")

    print(json.dumps({
        "passed": payload["passed"],
        "kind": payload["kind"],
        "selected_count": payload["selected_count"],
        "total_selected_chars": payload["total_selected_chars"],
        "output": str(output_path),
        "markdown_output": str(markdown_path),
        "warnings": payload["warnings"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
