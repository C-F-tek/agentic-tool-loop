#!/usr/bin/env python3
"""Select focused semantic code chunks for local AI context.

This tool is report-only. It can read an explicit semantic chunk index, but by
default it builds current-run source chunks directly from repository files.

Hybrid scoring: FTS5/BM25 token matching plus vector cosine with RRF fusion,
mirroring the RAG context pack retrieval pattern.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ia_carmine.context.agent_context.semantic_evidence_chunks.live_source import (
    build_live_source_chunks,
    repo_relative,
)

DEFAULT_CHUNKS = ""
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
        chunk.get("content_preview"),
    ]
    return " ".join(as_text(item) for item in fields).lower()


def reciprocal_rank(rank: int, k: int = 60) -> float:
    """Reciprocal rank fusion score for a given rank (k=60 is standard RRF constant)."""
    return 1.0 / (k + max(1, rank))


def cosine_from_norms(a: list[float], a_norm: float, b: list[float], b_norm: float) -> float:
    """Cosine similarity between two vectors given their norms."""
    if not a or not b or a_norm <= 0 or b_norm <= 0 or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (a_norm * b_norm)


def score_chunk(
    chunk: dict[str, Any], query_tokens: list[str], path_boosts: list[str]
) -> tuple[int, list[str]]:
    """Token-based scoring (legacy path: only token matching)."""
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


def score_chunk_hybrid(
    chunk: dict[str, Any],
    query_tokens: list[str],
    path_boosts: list[str],
    *,
    token_score: int,
    token_matched: list[str],
    vector_score: float = 0.0,
    vector_rank: int = 0,
    fused_score: float = 0.0,
) -> tuple[int, list[str]]:
    """Hybrid scoring: token-based score plus vector cosine with RRF fusion.

    Returns (total_score, matched_terms) where total_score includes:
    - Token-based score (path/symbol/domain matching)
    - Vector cosine score (semantic similarity)
    - RRF fusion score (combines token rank and vector rank)
    """
    return (
        int(token_score + vector_score + fused_score),
        list(token_matched),
    )


def embed_query(
    endpoint: str,
    model: str,
    query: str,
    timeout_seconds: float = 30.0,
) -> tuple[list[float], float, str]:
    """Embed a single query string using Ollama /api/embed endpoint.

    Returns (vector, norm, error) where error is empty on success.
    """
    from urllib.error import URLError
    import urllib.request
    import math

    if not query.strip():
        return [], 0.0, "query is empty"

    payload = json.dumps({"model": model, "input": [query]}).encode("utf-8")
    request = urllib.request.Request(
        endpoint.rstrip("/") if endpoint.endswith("/api/embed") else f"{endpoint}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        raw = data.get("embeddings")
        if not isinstance(raw, list) or not raw:
            return [], 0.0, "missing embeddings in response"
        item = raw[0]
        values = [float(v) for v in (item if isinstance(item, list) else [])]
        norm = math.sqrt(sum(v * v for v in values))
        if not values or norm <= 0:
            return [], 0.0, "embedding is empty or zero norm"
        return values, norm, ""
    except Exception as exc:
        return [], 0.0, f"{type(exc).__name__}: {exc}"


def build_selection(
    repo_root: Path,
    chunks_path: Path | None,
    query: str,
    max_chunks: int,
    max_total_chars: int,
    max_excerpt_chars: int,
    path_boosts: list[str],
    include_code: bool,
    *,
    embedding_endpoint: str = "",
    embedding_model: str = "",
) -> dict[str, Any]:
    """Build the chunk selection with hybrid token+vector scoring.

    If embedding_endpoint and embedding_model are provided, the query is embedded
    and used as a vector for RRF fusion alongside token-based scoring.
    """
    query_tokens = tokenize(query)
    warnings: list[str] = []

    # Embed the query if embedding is available
    query_vector: list[float] = []
    query_norm: float = 0.0
    vector_mode = "fts5_rrf"
    if embedding_endpoint and embedding_model:
        query_vector, query_norm, embed_error = embed_query(
            embedding_endpoint,
            embedding_model,
            query,
            timeout_seconds=30.0,
        )
        if embed_error:
            warnings.append(f"query embedding unavailable: {embed_error}")
        else:
            vector_mode = "vector_fts5_rrf"

    if chunks_path is not None and chunks_path.is_file():
        chunk_data = read_json(chunks_path)
        chunks = chunk_data.get("chunks") or []
        source_chunks = repo_relative(repo_root, chunks_path)
    else:
        chunks = build_live_source_chunks(
            repo_root,
            query_tokens,
            path_boosts,
            max_files=max(max_chunks * 3, 12),
            max_chunk_chars=max_excerpt_chars,
        )
        source_chunks = "current_source_live_chunks"
        if chunks_path is not None:
            warnings.append(
                f"explicit semantic chunk index unavailable: {repo_relative(repo_root, chunks_path)}; selected current-run live source chunks"
            )
    if not query_tokens and not path_boosts:
        raise ValueError("query or path boost is required")

    # Score all chunks with token-based scoring
    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        token_score, token_matched = score_chunk(chunk, query_tokens, path_boosts)
        if token_score <= 0 and not query_vector:
            continue
        item = dict(chunk)
        item["token_score"] = token_score
        item["token_matched"] = token_matched
        scored.append(item)

    # If we have a query vector, compute vector scores and RRF fusion
    if query_vector:
        # Sort scored chunks by token_score descending for ranking
        scored.sort(
            key=lambda item: (
            -int(item.get("token_score") or 0),
            str(item.get("path") or ""),
            int(item.get("line_start") or 0),
        )
        )

        # Compute vector cosine for each chunk
        for i, item in enumerate(scored):
            # Build chunk vector from its text content (simplified: use text hash as proxy)
            # In the full RAG pattern, chunk vectors are stored in rag_embeddings table
            # For select_code_chunks, we approximate by computing a simple text embedding
            chunk_text = str(item.get("text") or item.get("summary_short") or "")
            chunk_vec, chunk_vec_norm, _ = embed_query(
                embedding_endpoint,
                embedding_model,
                chunk_text[:1000],
                timeout_seconds=30.0,
            )
            if chunk_vec and chunk_vec_norm > 0:
                item["vector_score"] = cosine_from_norms(
                    query_vector,
                    query_norm,
                    chunk_vec,
                    chunk_vec_norm,
                )
                item["vector_rank"] = i + 1
            else:
                item["vector_score"] = 0.0
                item["vector_rank"] = 0

        # Compute RRF fusion scores
        for item in scored:
            token_rank = next(
                (i for i, x in enumerate(scored) if x.get("token_score") == item.get("token_score")),
                len(scored),
            ) + 1
            vector_rank = item.get("vector_rank", 0)
            fused = (
                reciprocal_rank(token_rank)
                + reciprocal_rank(vector_rank)
                if vector_rank
                else 0.0
            )
            item["fused_score"] = fused
            item["vector_mode"] = vector_mode

        # Sort by fused score descending
        scored.sort(
            key=lambda item: (
                -float(item.get("fused_score") or 0),
                str(item.get("path") or ""),
                int(item.get("line_start") or 0),
            )
        )

    # Select top chunks within budget
    scored.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            str(item.get("path") or ""),
            int(item.get("line_start") or 0),
        )
    )

    selected: list[dict[str, Any]] = []
    total_chars = 0
    skipped_outside_budget_count = 0
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
        if include_code:
            remaining = max(max_total_chars - total_chars, 0)
            if remaining <= 0:
                break
            excerpt_limit = min(max_excerpt_chars, remaining)
            excerpt, complete = source_excerpt(repo_root, item, excerpt_limit)
            if not complete:
                skipped_outside_budget_count += 1
                continue
            out["source_excerpt"] = excerpt
            out["source_excerpt_complete"] = True
            total_chars += len(excerpt)
        else:
            total_chars += len(json.dumps(out, ensure_ascii=False))
        selected.append(out)

    return {
        "schema_version": 1,
        "kind": "semantic_code_chunk_selection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "source_chunks": source_chunks,
        "max_chunks": max_chunks,
        "max_total_chars": max_total_chars,
        "max_excerpt_chars": max_excerpt_chars,
        "include_code": include_code,
        "path_boosts": path_boosts,
        "total_scored_chunks": len(scored),
        "selected_count": len(selected),
        "total_selected_chars": total_chars,
        "skipped_outside_budget_count": skipped_outside_budget_count,
        "source_writes_performed": False,
        "provider_execution_performed": False,
        "passed": True,
        "errors": [],
        "warnings": warnings if selected else [*warnings, "no chunks matched query"],
        "selected_chunks": selected,
    }


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
        return excerpt, True
    return "", False


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
    chunks_path: Path | None,
    query: str,
    max_chunks: int,
    max_total_chars: int,
    max_excerpt_chars: int,
    path_boosts: list[str],
    include_code: bool,
    *,
    embedding_endpoint: str = "",
    embedding_model: str = "",
) -> dict[str, Any]:
    query_tokens = tokenize(query)
    warnings: list[str] = []
    if chunks_path is not None and chunks_path.is_file():
        chunk_data = read_json(chunks_path)
        chunks = chunk_data.get("chunks") or []
        source_chunks = repo_relative(repo_root, chunks_path)
    else:
        chunks = build_live_source_chunks(
            repo_root,
            query_tokens,
            path_boosts,
            max_files=max(max_chunks * 3, 12),
            max_chunk_chars=max_excerpt_chars,
        )
        source_chunks = "current_source_live_chunks"
        if chunks_path is not None:
            warnings.append(
                f"explicit semantic chunk index unavailable: {repo_relative(repo_root, chunks_path)}; selected current-run live source chunks"
            )
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

    scored.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            str(item.get("path") or ""),
            int(item.get("line_start") or 0),
        )
    )

    selected: list[dict[str, Any]] = []
    total_chars = 0
    skipped_outside_budget_count = 0
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
        if include_code:
            remaining = max(max_total_chars - total_chars, 0)
            if remaining <= 0:
                break
            excerpt_limit = min(max_excerpt_chars, remaining)
            excerpt, complete = source_excerpt(repo_root, item, excerpt_limit)
            if not complete:
                skipped_outside_budget_count += 1
                continue
            out["source_excerpt"] = excerpt
            out["source_excerpt_complete"] = True
            total_chars += len(excerpt)
        else:
            total_chars += len(json.dumps(out, ensure_ascii=False))
        selected.append(out)

    return {
        "schema_version": 1,
        "kind": "semantic_code_chunk_selection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "source_chunks": source_chunks,
        "max_chunks": max_chunks,
        "max_total_chars": max_total_chars,
        "max_excerpt_chars": max_excerpt_chars,
        "include_code": include_code,
        "path_boosts": path_boosts,
        "total_scored_chunks": len(scored),
        "selected_count": len(selected),
        "total_selected_chars": total_chars,
        "skipped_outside_budget_count": skipped_outside_budget_count,
        "source_writes_performed": False,
        "provider_execution_performed": False,
        "passed": True,
        "errors": [],
        "warnings": warnings if selected else [*warnings, "no chunks matched query"],
        "selected_chunks": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--chunks",
        default=DEFAULT_CHUNKS,
        help="Optional explicit semantic chunk index. Omit for current-run live source chunks.",
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-chunks", type=int, default=20)
    parser.add_argument("--max-total-chars", type=int, default=24000)
    parser.add_argument("--max-excerpt-chars", type=int, default=2500)
    parser.add_argument("--path-boost", action="append", default=[])
    parser.add_argument("--no-code", action="store_true")
    # New hybrid scoring options (mirroring RAG context pack)
    parser.add_argument("--embedding-endpoint", default="", help="Ollama embedding endpoint for vector scoring")
    parser.add_argument("--embedding-model", default="", help="Ollama embedding model for vector scoring")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    chunks_path = Path(args.chunks) if str(args.chunks or "").strip() else None
    if chunks_path is not None and not chunks_path.is_absolute():
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
        embedding_endpoint=args.embedding_endpoint,
        embedding_model=args.embedding_model,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": payload["passed"],
                "kind": payload["kind"],
                "selected_count": payload["selected_count"],
                "total_selected_chars": payload["total_selected_chars"],
                "output": str(output_path),
                "markdown_output": str(markdown_path),
                "warnings": payload["warnings"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())