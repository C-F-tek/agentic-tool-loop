"""Manifest builder for Full0To10 SQLite memory."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .schema import init_schema


def scalar(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def build_memory_manifest(conn: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    init_schema(conn)
    namespaces = [
        row[0]
        for row in conn.execute("SELECT namespace FROM memory_chunks GROUP BY namespace ORDER BY namespace").fetchall()
    ]
    return {
        "kind": "full0to10_sqlite_memory_manifest",
        "passed": True,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "content_included": False,
        "git_trackable": False,
        "item_count": scalar(conn, "SELECT COUNT(*) FROM memory_items"),
        "chunk_count": scalar(conn, "SELECT COUNT(*) FROM memory_chunks"),
        "embedding_cache_count": scalar(conn, "SELECT COUNT(*) FROM embedding_cache"),
        "namespaces": namespaces,
        "persistent_memory_write_performed": False,
    }
