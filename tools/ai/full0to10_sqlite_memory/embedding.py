"""Embedding cache and providers for Full0To10 SQLite memory."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .ingest import sha256_text
from .schema import init_schema


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_embedding(text: str, dimension: int = 64) -> list[float]:
    values: list[float] = []
    seed = text.encode("utf-8", errors="replace")
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) >= dimension:
                break
        counter += 1
    return normalize(values)


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[i] * right[i] for i in range(size))


def get_cached(conn: sqlite3.Connection, text_hash: str, model: str) -> list[float] | None:
    row = conn.execute(
        "SELECT embedding_json FROM embedding_cache WHERE text_hash = ? AND model = ?",
        (text_hash, model),
    ).fetchone()
    if not row or not row["embedding_json"]:
        return None
    return [float(value) for value in json.loads(row["embedding_json"])]


def put_cached(conn: sqlite3.Connection, text_hash: str, model: str, vector: list[float]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO embedding_cache(text_hash, model, dimension, embedding_json, created_at)
        VALUES(?, ?, ?, ?, ?)
        """,
        (text_hash, model, len(vector), json.dumps(vector), utc_now()),
    )
    conn.commit()


def ollama_embedding(text: str, model: str, ollama_url: str, timeout: int = 20) -> list[float]:
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - localhost operator endpoint.
        data = json.loads(response.read().decode("utf-8"))
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("Ollama embedding response missing embedding list")
    return normalize([float(value) for value in embedding])


def embedding_for_text(
    conn: sqlite3.Connection,
    text: str,
    model: str,
    provider: str,
    ollama_url: str,
) -> tuple[list[float], bool]:
    init_schema(conn)
    text_hash = sha256_text(text)
    cached = get_cached(conn, text_hash, model)
    if cached is not None:
        return cached, True
    if provider == "ollama":
        vector = ollama_embedding(text, model, ollama_url)
    else:
        vector = hash_embedding(text)
    put_cached(conn, text_hash, model, vector)
    return vector, False


def embed_missing_chunks(
    conn: sqlite3.Connection,
    namespace: str,
    model: str,
    provider: str,
    ollama_url: str,
    limit: int,
) -> dict[str, Any]:
    init_schema(conn)
    rows = conn.execute(
        """
        SELECT id, text, text_hash FROM memory_chunks
        WHERE namespace = ?
        ORDER BY chunk_index
        LIMIT ?
        """,
        (namespace, limit),
    ).fetchall()
    hits = 0
    misses = 0
    for row in rows:
        _, cached = embedding_for_text(conn, row["text"], model, provider, ollama_url)
        if cached:
            hits += 1
        else:
            misses += 1
    return {
        "kind": "memory_embed_missing",
        "passed": True,
        "namespace": namespace,
        "model": model,
        "provider": provider,
        "processed": len(rows),
        "cache_hits": hits,
        "cache_misses": misses,
        "provider_execution_performed": provider == "ollama" and misses > 0,
    }
