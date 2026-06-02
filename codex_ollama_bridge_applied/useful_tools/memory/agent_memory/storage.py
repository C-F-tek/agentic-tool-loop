"""Persistent memory JSONL and SQLite storage helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .common import (
    MEMORY_DB_SCHEMA_VERSION,
    json_or_default,
    read_text,
    relative_path,
    sha256_text,
)
from .models import MemoryRecord

def load_memory_jsonl(path: Path) -> list[MemoryRecord]:
    """Load persistent memory records from JSONL."""
    if not path.exists():
        return []
    records: list[MemoryRecord] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = MemoryRecord.from_mapping(json.loads(line))
        except json.JSONDecodeError:
            record = None
        if record is not None:
            records.append(record)
    return records

def append_memory_jsonl(path: Path, record: MemoryRecord) -> None:
    """Append one persistent memory record to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

def ensure_memory_db(path: Path) -> None:
    """Create or upgrade a lightweight SQLite memory database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                expires_at TEXT,
                metadata_json TEXT NOT NULL
            )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_records(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_records(scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_records(source)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """)
        conn.execute(
            "INSERT OR REPLACE INTO memory_meta(key, value) VALUES('schema_version', ?)",
            (str(MEMORY_DB_SCHEMA_VERSION),),
        )

def upsert_memory_db(path: Path, records: Iterable[MemoryRecord]) -> int:
    """Insert or update records in the SQLite memory database."""
    ensure_memory_db(path)
    count = 0
    with sqlite3.connect(path) as conn:
        for record in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_records (
                    record_id, kind, scope, source, summary, content, tags_json,
                    confidence, created_at, updated_at, expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.kind,
                    record.scope,
                    record.source,
                    record.summary,
                    record.content,
                    json.dumps(list(record.tags), ensure_ascii=False),
                    record.confidence,
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            count += 1
    return count

def load_memory_db(path: Path, *, limit: int = 1000) -> list[MemoryRecord]:
    """Load records from the SQLite memory database."""
    if not path.exists():
        return []
    records: list[MemoryRecord] = []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT record_id, kind, scope, source, summary, content, tags_json,
                   confidence, created_at, updated_at, expires_at, metadata_json
            FROM memory_records
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (int(limit),),
        ):
            tags = json_or_default(row["tags_json"], [])
            metadata = json_or_default(row["metadata_json"], {})
            records.append(
                MemoryRecord(
                    record_id=row["record_id"],
                    kind=row["kind"],
                    scope=row["scope"],
                    source=row["source"],
                    summary=row["summary"],
                    content=row["content"],
                    tags=tuple(str(tag) for tag in tags if str(tag).strip()),
                    confidence=float(row["confidence"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                    metadata=dict(metadata),
                )
            )
    return records

def records_from_files(
    paths: Iterable[Path], repo_root: Path, max_record_chars: int
) -> list[MemoryRecord]:
    """Create file-backed memory records for included source files."""
    records: list[MemoryRecord] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        rel = relative_path(path, repo_root)
        text = read_text(path)
        tags = ("source_file", path.suffix.lower().lstrip(".") or "text")
        records.append(
            MemoryRecord.from_text(
                kind="source_file",
                scope="project",
                source=rel,
                text=text,
                tags=tags,
                max_record_chars=max_record_chars,
                metadata={
                    "path": rel,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_text(text),
                },
            )
        )
    return records
