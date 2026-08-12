"""Ingestion commands for Full0To10 SQLite memory."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .chunker import chunk_markdown, chunk_plain
from .constants import DENY_SUFFIXES
from .schema import init_schema


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_item(
    conn: sqlite3.Connection,
    namespace: str,
    source_type: str,
    source_path: str | None,
    title: str | None,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_schema(conn)
    item_id = uuid4().hex
    chunks = chunk_markdown(text) if source_path and source_path.lower().endswith(".md") else chunk_plain(text)
    conn.execute(
        """
        INSERT INTO memory_items(id, namespace, source_type, source_path, title, content_hash, created_at, metadata_json)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, namespace, source_type, source_path, title, sha256_text(text), utc_now(), json.dumps(metadata or {})),
    )
    for chunk in chunks:
        chunk_id = uuid4().hex
        text_hash = sha256_text(chunk.text)
        conn.execute(
            """
            INSERT INTO memory_chunks(id, item_id, namespace, chunk_index, text, text_hash, heading_path, metadata_json)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, item_id, namespace, chunk.chunk_index, chunk.text, text_hash, chunk.heading_path, "{}"),
        )
        conn.execute(
            "INSERT INTO memory_chunks_fts(chunk_id, namespace, heading_path, text) VALUES(?, ?, ?, ?)",
            (chunk_id, namespace, chunk.heading_path, chunk.text),
        )
    conn.commit()
    return {"item_id": item_id, "chunk_count": len(chunks), "content_hash": sha256_text(text)}


def memory_add_text(conn: sqlite3.Connection, namespace: str, text: str, title: str | None = None) -> dict[str, Any]:
    result = insert_item(conn, namespace, "text", None, title, text)
    return {"kind": "memory_add_text", "passed": True, "namespace": namespace, **result}


def memory_add_file(conn: sqlite3.Connection, namespace: str, path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in DENY_SUFFIXES:
        return {"kind": "memory_add_file", "passed": False, "path": str(path), "errors": ["database files are denied"]}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    result = insert_item(conn, namespace, "file", str(path), path.name, text)
    return {"kind": "memory_add_file", "passed": True, "namespace": namespace, "path": str(path), **result}
