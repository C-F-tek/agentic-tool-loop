#!/usr/bin/env python3
"""Create SQLite DB for embeddings."""
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("USERPROFILE", Path.home())) / "AI" / "state" / "codex_rag" / "embeddings.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

print(f"Creating DB at: {DB_PATH}")

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Create embeddings table
cursor.execute("""
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol TEXT,
    kind TEXT,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT
)
""")

# Create FTS5 virtual table for search (without tokenizers - not supported in this SQLite version)
cursor.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_fts USING fts5(content)
""")

conn.commit()
print("DB created successfully")
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"Tables: {tables}")

conn.close()