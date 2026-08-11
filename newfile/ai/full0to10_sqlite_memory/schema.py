"""Schema management for Full0To10 SQLite memory."""
from __future__ import annotations

import sqlite3

from .constants import SCHEMA_VERSION


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_items (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_path TEXT,
            title TEXT,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS memory_chunks (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            heading_path TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(item_id) REFERENCES memory_items(id)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            namespace UNINDEXED,
            heading_path,
            text,
            tokenize='unicode61'
        );

        CREATE TABLE IF NOT EXISTS embedding_cache (
            text_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            dimension INTEGER,
            embedding_json TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(text_hash, model)
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
