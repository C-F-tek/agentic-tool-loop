"""Hybrid RAG retrieval: FTS5/BM25 plus vector cosine with RRF fusion."""

from __future__ import annotations

from typing import Any

from .common import DEFAULT_FUSION_K
from .embedding import cosine_from_norms
from .store import embedding_rows, fts_search


def reciprocal_rank(rank: int, k: int = DEFAULT_FUSION_K) -> float:
    return 1.0 / (k + max(1, int(rank)))


def vector_search(
    conn: Any,
    *,
    query_vector: list[float],
    query_norm: float,
    model: str,
    endpoint: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = embedding_rows(conn, model=model, endpoint=endpoint)
    scored: list[dict[str, Any]] = []
    for row in rows:
        score = cosine_from_norms(
            query_vector,
            query_norm,
            list(row.get("embedding") or []),
            float(row.get("vector_norm") or 0.0),
        )
        row = dict(row)
        row.pop("embedding", None)
        row["vector_score"] = score
        scored.append(row)
    return sorted(scored, key=lambda item: float(item["vector_score"]), reverse=True)[:limit]


def hybrid_search(
    conn: Any,
    *,
    query: str,
    query_vector: list[float] | None,
    query_norm: float,
    model: str,
    endpoint: str,
    top_k: int,
    char_budget: int,
    per_file_limit: int = 4,
) -> list[dict[str, Any]]:
    candidate_limit = max(top_k * 4, 40)
    fts_rows = fts_search(conn, query, candidate_limit)
    vector_rows = (
        vector_search(
            conn,
            query_vector=query_vector,
            query_norm=query_norm,
            model=model,
            endpoint=endpoint,
            limit=candidate_limit,
        )
        if query_vector
        else []
    )
    fused: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(fts_rows, start=1):
        item = fused.setdefault(row["chunk_id"], dict(row))
        item["fts_rank"] = rank
        item["bm25"] = row.get("bm25")
        item["fused_score"] = float(item.get("fused_score") or 0.0) + reciprocal_rank(rank)
    for rank, row in enumerate(vector_rows, start=1):
        item = fused.setdefault(row["chunk_id"], dict(row))
        item["vector_rank"] = rank
        item["vector_score"] = row.get("vector_score")
        item["fused_score"] = float(item.get("fused_score") or 0.0) + reciprocal_rank(rank)
    selected: list[dict[str, Any]] = []
    chars = 0
    per_file: dict[str, int] = {}
    for item in sorted(fused.values(), key=lambda row: float(row["fused_score"]), reverse=True):
        source = str(item.get("source_path") or "")
        if per_file.get(source, 0) >= per_file_limit:
            continue
        text = str(item.get("text") or "")
        if selected and chars + len(text) > char_budget:
            continue
        item["selected_chars"] = len(text)
        selected.append(item)
        chars += len(text)
        per_file[source] = per_file.get(source, 0) + 1
        if len(selected) >= top_k:
            break
    return selected

