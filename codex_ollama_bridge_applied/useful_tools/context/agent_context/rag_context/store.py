"""SQLite store operations for RAG ingest and retrieval."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .common import language_for_suffix, now_iso, sha256_text
from .embedding import pack_vector, unpack_vector
from .schema import ensure_schema


def connect(db_path: Path) -> sqlite3.Connection:
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_document_chunks(
    conn: sqlite3.Connection,
    *,
    source_path: str,
    file_size: int,
    mtime_ns: int,
    suffix: str,
    content_hash: str,
    chunks: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    document_id = sha256_text(source_path)[:32]
    row = conn.execute(
        "SELECT content_hash, first_seen_at FROM rag_documents WHERE source_path=?",
        (source_path,),
    ).fetchone()
    first_seen = str(row["first_seen_at"]) if row else timestamp
    changed = not row or str(row["content_hash"]) != content_hash
    conn.execute(
        """
        INSERT OR REPLACE INTO rag_documents (
          document_id, source_path, file_size, mtime_ns, content_hash, suffix,
          language, status, first_seen_at, last_indexed_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            source_path,
            file_size,
            mtime_ns,
            content_hash,
            suffix,
            language_for_suffix(suffix),
            "active",
            first_seen,
            timestamp,
            json.dumps(metadata, ensure_ascii=False),
        ),
    )
    if changed:
        conn.execute("UPDATE rag_chunks SET active=0 WHERE document_id=?", (document_id,))
    inserted = 0
    for chunk in chunks:
        metadata_json = json.dumps(chunk.get("metadata") or {}, ensure_ascii=False)
        conn.execute(
            """
            INSERT OR REPLACE INTO rag_chunks (
              chunk_id, document_id, source_path, chunk_index, char_start, char_end,
              text, text_hash, content_hash, chunk_policy_hash, active, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                chunk["chunk_id"],
                document_id,
                source_path,
                int(chunk["chunk_index"]),
                int(chunk["char_start"]),
                int(chunk["char_end"]),
                chunk["text"],
                chunk["text_hash"],
                chunk["content_hash"],
                chunk["chunk_policy_hash"],
                metadata_json,
            ),
        )
        conn.execute("DELETE FROM rag_chunks_fts WHERE chunk_id=?", (chunk["chunk_id"],))
        conn.execute(
            "INSERT INTO rag_chunks_fts(chunk_id, source_path, text, metadata_json) VALUES (?, ?, ?, ?)",
            (chunk["chunk_id"], source_path, chunk["text"], metadata_json),
        )
        inserted += 1
    return {"document_id": document_id, "changed": changed, "chunk_count": inserted}


def missing_embedding_chunks(
    conn: sqlite3.Connection,
    *,
    model: str,
    endpoint: str,
    limit: int = 0,
) -> list[dict[str, Any]]:
    query = """
        SELECT c.chunk_id, c.source_path, c.chunk_index, c.text, c.text_hash
        FROM rag_chunks AS c
        LEFT JOIN rag_embeddings AS e
          ON e.chunk_id = c.chunk_id
         AND e.embedding_model = ?
         AND e.embedding_endpoint = ?
        WHERE c.active = 1 AND e.chunk_id IS NULL
        ORDER BY c.source_path, c.chunk_index
    """
    if limit > 0:
        query += " LIMIT ?"
        rows = conn.execute(query, (model, endpoint, int(limit))).fetchall()
    else:
        rows = conn.execute(query, (model, endpoint)).fetchall()
    return [dict(row) for row in rows]


def insert_embedding(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    model: str,
    endpoint: str,
    vector: list[float],
    norm: float,
    metadata: dict[str, Any] | None = None,
) -> None:
    blob = pack_vector(vector)
    conn.execute(
        """
        INSERT OR REPLACE INTO rag_embeddings (
          chunk_id, embedding_model, embedding_endpoint, dimension,
          embedding_blob, vector_norm, embedding_hash, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            model,
            endpoint,
            len(vector),
            blob,
            norm,
            sha256_text(blob.hex()),
            now_iso(),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def mark_absent_documents_inactive(
    conn: sqlite3.Connection, active_source_paths: set[str]
) -> int:
    rows = conn.execute(
        "SELECT document_id, source_path FROM rag_documents WHERE status='active'"
    ).fetchall()
    absent = [
        (str(row["document_id"]), str(row["source_path"]))
        for row in rows
        if str(row["source_path"]) not in active_source_paths
    ]
    for document_id, _source_path in absent:
        conn.execute(
            "UPDATE rag_documents SET status='inactive', last_indexed_at=? WHERE document_id=?",
            (now_iso(), document_id),
        )
        conn.execute("UPDATE rag_chunks SET active=0 WHERE document_id=?", (document_id,))
    return len(absent)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_./:-]{2,}", query or "")
    if not tokens:
        return '"' + query.replace('"', '""') + '"'
    return " OR ".join(f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens[:24])


def fts_search(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    quoted = _fts_query(query)
    rows = conn.execute(
        """
        SELECT c.chunk_id, c.source_path, c.chunk_index, c.char_start, c.char_end,
               c.text, c.text_hash, bm25(rag_chunks_fts) AS bm25
        FROM rag_chunks_fts
        JOIN rag_chunks AS c ON c.chunk_id = rag_chunks_fts.chunk_id
        WHERE rag_chunks_fts MATCH ? AND c.active = 1
        ORDER BY bm25(rag_chunks_fts)
        LIMIT ?
        """,
        (quoted, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def embedding_rows(
    conn: sqlite3.Connection, *, model: str, endpoint: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.chunk_id, c.source_path, c.chunk_index, c.char_start, c.char_end,
               c.text, c.text_hash, e.dimension, e.embedding_blob, e.vector_norm
        FROM rag_embeddings AS e
        JOIN rag_chunks AS c ON c.chunk_id = e.chunk_id
        WHERE c.active = 1 AND e.embedding_model = ? AND e.embedding_endpoint = ?
        """,
        (model, endpoint),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["embedding"] = unpack_vector(item.pop("embedding_blob"), int(item["dimension"]))
        out.append(item)
    return out


def record_retrieval_event(
    conn: sqlite3.Connection,
    *,
    context_pack_id: str,
    query: str,
    top_k: int,
    char_budget: int,
    config: dict[str, Any],
    selected_chunk_ids: list[str],
    warnings: list[str],
) -> str:
    event_id = sha256_text(f"{context_pack_id}:{query}:{now_iso()}")[:32]
    conn.execute(
        """
        INSERT INTO rag_retrieval_events (
          event_id, context_pack_id, created_at, query, query_hash, top_k,
          char_budget, config_json, selected_chunk_ids_json, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            context_pack_id,
            now_iso(),
            query,
            sha256_text(query),
            int(top_k),
            int(char_budget),
            json.dumps(config, ensure_ascii=False),
            json.dumps(selected_chunk_ids, ensure_ascii=False),
            json.dumps(warnings, ensure_ascii=False),
        ),
    )
    return event_id


def status(conn: sqlite3.Connection) -> dict[str, Any]:
    def count(table: str) -> int:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    return {
        "document_count": count("rag_documents"),
        "active_chunk_count": int(
            conn.execute("SELECT count(*) FROM rag_chunks WHERE active=1").fetchone()[0]
        ),
        "embedding_count": count("rag_embeddings"),
        "retrieval_event_count": count("rag_retrieval_events"),
    }
