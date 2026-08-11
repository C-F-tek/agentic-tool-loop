"""Constants for Full0To10 SQLite memory."""
from __future__ import annotations

SCHEMA_VERSION = 1
DEFAULT_NAMESPACE = "default"
MAX_CHUNK_CHARS = 4000
CHUNK_OVERLAP_CHARS = 400
DENY_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
)
TEXT_SUFFIXES = (
    ".md",
    ".txt",
    ".json",
    ".py",
    ".ps1",
)
