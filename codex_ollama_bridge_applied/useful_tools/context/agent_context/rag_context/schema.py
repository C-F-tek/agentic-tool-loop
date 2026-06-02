"""SQLite schema for the internal RAG index."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .common import now_iso

SCHEMA_VERSION = 1


DDL = """
CREATE TABLE IF NOT EXISTS rag_schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_documents (
  document_id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL UNIQUE,
  file_size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  suffix TEXT NOT NULL,
  language TEXT NOT NULL,
  status TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_indexed_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  text TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  chunk_policy_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES rag_documents(document_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts
USING fts5(chunk_id UNINDEXED, source_path UNINDEXED, text, metadata_json);
CREATE TABLE IF NOT EXISTS rag_embeddings (
  chunk_id TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_endpoint TEXT NOT NULL,
  dimension INTEGER NOT NULL,
  embedding_blob BLOB NOT NULL,
  vector_norm REAL NOT NULL,
  embedding_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  PRIMARY KEY(chunk_id, embedding_model, embedding_endpoint),
  FOREIGN KEY(chunk_id) REFERENCES rag_chunks(chunk_id)
);
CREATE TABLE IF NOT EXISTS rag_retrieval_events (
  event_id TEXT PRIMARY KEY,
  context_pack_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  query TEXT NOT NULL,
  query_hash TEXT NOT NULL,
  top_k INTEGER NOT NULL,
  char_budget INTEGER NOT NULL,
  config_json TEXT NOT NULL,
  selected_chunk_ids_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source ON rag_chunks(source_path);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_active ON rag_chunks(active);
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_model ON rag_embeddings(embedding_model);
"""


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(DDL)
        conn.execute(
            "INSERT OR IGNORE INTO rag_schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
            (SCHEMA_VERSION, now_iso(), "initial rag sqlite/fts/vector schema"),
        )
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.commit()


def integrity_check(db_path: Path) -> str:
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "missing"
