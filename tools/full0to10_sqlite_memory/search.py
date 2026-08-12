"""FTS and hybrid search for Full0To10 SQLite memory."""
from __future__ import annotations

import sqlite3
from typing import Any

from .embedding import cosine, embedding_for_text
from .schema import init_schema


def fts_rows(conn: sqlite3.Connection, namespace: str, query: str, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT f.chunk_id, f.namespace, f.heading_path, f.text, c.text_hash, bm25(memory_chunks_fts) AS rank
        FROM memory_chunks_fts f
        JOIN memory_chunks c ON c.id = f.chunk_id
        WHERE memory_chunks_fts MATCH ? AND f.namespace = ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, namespace, limit),
    ).fetchall()


def all_namespace_rows(conn: sqlite3.Connection, namespace: str, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id AS chunk_id, namespace, heading_path, text, text_hash
        FROM memory_chunks
        WHERE namespace = ?
        ORDER BY chunk_index
        LIMIT ?
        """,
        (namespace, limit),
    ).fetchall()


def score_fts_rank(raw_rank: float) -> float:
    return 1.0 / (1.0 + abs(raw_rank))


def memory_search(
    conn: sqlite3.Connection,
    namespace: str,
    query: str,
    limit: int = 10,
    mode: str = "hybrid",
    embedding_model: str = "hash-local-v1",
    embedding_provider: str = "none",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict[str, Any]:
    init_schema(conn)
    use_embedding = mode == "hybrid" and embedding_provider != "none"
    rows = fts_rows(conn, namespace, query, limit)
    if use_embedding and len(rows) < limit:
        seen = {row["chunk_id"] for row in rows}
        rows.extend(row for row in all_namespace_rows(conn, namespace, limit * 2) if row["chunk_id"] not in seen)

    query_vector = None
    cache_hits = 0
    cache_misses = 0
    if use_embedding:
        query_vector, query_cached = embedding_for_text(conn, query, embedding_model, embedding_provider, ollama_url)
        cache_hits += 1 if query_cached else 0
        cache_misses += 0 if query_cached else 1

    results = []
    for row in rows:
        raw_rank = float(row["rank"]) if "rank" in row.keys() else 999.0
        fts_score = score_fts_rank(raw_rank)
        vector_score = None
        hybrid_score = fts_score
        if query_vector is not None:
            chunk_vector, cached = embedding_for_text(conn, row["text"], embedding_model, embedding_provider, ollama_url)
            cache_hits += 1 if cached else 0
            cache_misses += 0 if cached else 1
            vector_score = max(0.0, cosine(query_vector, chunk_vector))
            hybrid_score = (0.55 * vector_score) + (0.45 * fts_score)
        results.append(
            {
                "chunk_id": row["chunk_id"],
                "namespace": row["namespace"],
                "heading_path": row["heading_path"],
                "fts_score": fts_score,
                "vector_score": vector_score,
                "hybrid_score": hybrid_score,
                "text_preview": row["text"][:500],
            }
        )
    results.sort(key=lambda item: float(item["hybrid_score"]), reverse=True)
    return {
        "kind": "memory_search",
        "passed": True,
        "namespace": namespace,
        "query": query,
        "mode": mode,
        "embedding_model": embedding_model,
        "embedding_provider": embedding_provider,
        "result_count": len(results[:limit]),
        "embedding_cache_used": use_embedding,
        "embedding_cache_hits": cache_hits,
        "embedding_cache_misses": cache_misses,
        "results": results[:limit],
    }
