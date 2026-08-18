#!/usr/bin/env python3
"""Check FTS5 schema for embeddings table."""
import sqlite3
from pathlib import Path

db_path = Path.home() / "AI" / "state" / "codex_rag" / "embeddings.sqlite3"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check all tables
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("=== Tables ===")
for name, sql in tables:
    print(f"{name}: {sql}")

# Check FTS5 tables
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'")
fts_tables = cursor.fetchall()
print("\n=== FTS Tables ===")
for name, sql in fts_tables:
    print(f"{name}: {sql}")

# Check the embeddings_fts table structure
cursor.execute("PRAGMA table_info(embeddings_fts)")
cols = cursor.fetchall()
print("\n=== embeddings_fts columns ===")
for col in cols:
    print(col)

conn.close()