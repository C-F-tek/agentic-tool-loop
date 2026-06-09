#!/usr/bin/env python3
"""
Build a small, explicit SQLite/FTS5 code index for Codex RAG.

This indexer is intentionally independent from OpenWebUI/Chroma. It scans a
single repository root, stores bounded text chunks, and creates a deterministic
FTS5 table that can be read by services/codex_bridge/rag_mcp_server.py.

Default output:
  %USERPROFILE%/AI/state/codex_rag/code_rag.sqlite3
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "venvs",
    "node_modules",
    "dist",
    "build",
    "output",
    "outputs",
    "logs",
    "cache",
    ".cache",
    "openwebui-data",
    "models-task",
    "models-ovms-rerank",
    "ovms-runtime",
}

DEFAULT_SUFFIXES = {
    ".py",
    ".pyi",
    ".ps1",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".ini",
    ".cfg",
    ".env",
    ".sh",
    ".bat",
    ".cmd",
}

MAX_FILE_BYTES_DEFAULT = 2_000_000
CHUNK_LINES_DEFAULT = 180
CHUNK_CHARS_DEFAULT = 12_000


def _default_db() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _iter_files(root: Path, suffixes: set[str], exclude_dirs: set[str], max_file_bytes: int) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_dirs and not d.startswith(".git")
        ]

        for filename in filenames:
            path = current / filename
            suffix = path.suffix.lower()
            if suffix not in suffixes:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield path


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if b"\x00" in data[:4096]:
        return None

    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def _guess_symbol(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            return stripped.split(":", 1)[0][:240]
        if stripped.startswith("class "):
            return stripped.split(":", 1)[0][:240]
        if stripped.startswith("function "):
            return stripped.split("{", 1)[0][:240]
    return ""


def _chunk_lines(text: str, max_lines: int, max_chars: int) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    start = 0
    while start < len(lines):
        end = min(len(lines), start + max_lines)
        chunk = "\n".join(lines[start:end]).strip()

        while len(chunk) > max_chars and end - start > 20:
            end = start + max(20, (end - start) // 2)
            chunk = "\n".join(lines[start:end]).strip()

        if chunk:
            yield start + 1, end, chunk

        start = end


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS chunks_ai;
        DROP TRIGGER IF EXISTS chunks_ad;
        DROP TRIGGER IF EXISTS chunks_au;
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS index_meta;

        CREATE TABLE index_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            repo_root TEXT NOT NULL,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            symbol TEXT,
            kind TEXT,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE INDEX idx_chunks_path ON chunks(path);
        CREATE INDEX idx_chunks_hash ON chunks(content_hash);

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            path,
            symbol,
            kind,
            content,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, path, symbol, kind, content)
            VALUES (new.id, new.path, new.symbol, new.kind, new.content);
        END;

        CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content)
            VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content);
        END;

        CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content)
            VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content);
            INSERT INTO chunks_fts(rowid, path, symbol, kind, content)
            VALUES (new.id, new.path, new.symbol, new.kind, new.content);
        END;
        """
    )


def build_index(
    repo_root: Path,
    db: Path,
    suffixes: set[str],
    exclude_dirs: set[str],
    max_file_bytes: int,
    chunk_lines: int,
    chunk_chars: int,
) -> dict[str, int | str]:
    repo_root = repo_root.resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise FileNotFoundError(f"repository root not found: {repo_root}")

    conn = _connect(db)
    now = int(time.time())
    file_count = 0
    chunk_count = 0

    try:
        _init_schema(conn)
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("repo_root", str(repo_root)))
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("indexed_at", str(now)))
        conn.execute("INSERT INTO index_meta(key, value) VALUES (?, ?)", ("index_version", "1"))

        for path in _iter_files(repo_root, suffixes, exclude_dirs, max_file_bytes):
            text = _read_text(path)
            if text is None or not text.strip():
                continue

            rel = path.relative_to(repo_root).as_posix()
            kind = path.suffix.lower().lstrip(".") or "text"
            file_count += 1

            for start_line, end_line, content in _chunk_lines(text, chunk_lines, chunk_chars):
                digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
                symbol = _guess_symbol(content.splitlines()[:80])
                conn.execute(
                    """
                    INSERT INTO chunks(
                        repo_root, path, start_line, end_line, symbol,
                        kind, content, content_hash, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(repo_root), rel, start_line, end_line, symbol, kind, content, digest, now),
                )
                chunk_count += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "db": str(db),
        "repo_root": str(repo_root),
        "files_indexed": file_count,
        "chunks_indexed": chunk_count,
    }


def _parse_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Codex RAG SQLite/FTS5 index.")
    parser.add_argument("--repo", default=os.environ.get("AICARMINE_RAG_REPO") or os.environ.get("AICARMINE_LAB_REPO") or ".")
    parser.add_argument("--db", default=os.environ.get("AICARMINE_RAG_DB") or str(_default_db()))
    parser.add_argument("--suffixes", default=",".join(sorted(DEFAULT_SUFFIXES)))
    parser.add_argument("--exclude-dirs", default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)))
    parser.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES_DEFAULT)
    parser.add_argument("--chunk-lines", type=int, default=CHUNK_LINES_DEFAULT)
    parser.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS_DEFAULT)
    args = parser.parse_args(argv)

    result = build_index(
        repo_root=Path(args.repo),
        db=Path(args.db),
        suffixes=_parse_csv(args.suffixes),
        exclude_dirs=_parse_csv(args.exclude_dirs),
        max_file_bytes=max(1, args.max_file_bytes),
        chunk_lines=max(20, args.chunk_lines),
        chunk_chars=max(1000, args.chunk_chars),
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())