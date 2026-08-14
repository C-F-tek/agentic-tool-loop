#!/usr/bin/env python3
"""
Build a small, explicit SQLite/FTS5 code index for Codex RAG.

This indexer is intentionally independent from OpenWebUI/Chroma. By default it
indexes the Git candidate surface (`git ls-files --cached --others
--exclude-standard`), so .gitignore owns inclusion/exclusion. It stores bounded
text chunks, supports delta updates, and creates a deterministic FTS5 table
that can be read by services/codex_bridge/rag_mcp_server.py.

Default output:
  %USERPROFILE%/AI/state/codex_rag/code_rag.sqlite3
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

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
SOURCE_GIT_DEFAULT = "git"
SOURCE_FILESYSTEM = "filesystem"
MODE_DELTA = "delta"
MODE_FULL = "full"


def _default_db() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _git_candidate_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git ls-files failed"
        raise RuntimeError(stderr)

    paths: list[str] = []
    seen: set[str] = set()
    for item in result.stdout.split("\0"):
        rel = item.replace("\\", "/").strip("/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        paths.append(rel)
    return paths


def _iter_git_files(root: Path, suffixes: set[str], max_file_bytes: int) -> Iterable[Path]:
    for rel in _git_candidate_paths(root):
        path = root / rel
        if path.suffix.lower() not in suffixes:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if not path.is_file() or stat.st_size > max_file_bytes:
            continue
        yield path


def _iter_filesystem_files(root: Path, suffixes: set[str], max_file_bytes: int) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d != ".git"
            and not d.startswith("diag-")
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


def _iter_files(root: Path, suffixes: set[str], max_file_bytes: int, source: str) -> Iterable[Path]:
    if source == SOURCE_GIT_DEFAULT:
        yield from _iter_git_files(root, suffixes, max_file_bytes)
        return
    if source == SOURCE_FILESYSTEM:
        yield from _iter_filesystem_files(root, suffixes, max_file_bytes)
        return
    raise ValueError(f"unsupported source: {source}")


def _read_text(path: Path,  max_file_bytes: int | None = None) -> str | None:
    try:
        if max_file_bytes is not None and path.stat().st_size > max_file_bytes:
            return None
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


def _drop_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS chunks_ai;
        DROP TRIGGER IF EXISTS chunks_ad;
        DROP TRIGGER IF EXISTS chunks_au;
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS files;
        DROP TABLE IF EXISTS index_meta;
        """
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS index_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            chunks_count INTEGER NOT NULL,
            indexed_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
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

        CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
        CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(content_hash);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            path,
            symbol,
            kind,
            content,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, path, symbol, kind, content)
            VALUES (new.id, new.path, new.symbol, new.kind, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content)
            VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content)
            VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content);
            INSERT INTO chunks_fts(rowid, path, symbol, kind, content)
            VALUES (new.id, new.path, new.symbol, new.kind, new.content);
        END;
        """
    )


def _init_schema(conn: sqlite3.Connection) -> None:
    _drop_schema(conn)
    _ensure_schema(conn)


def _upsert_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO index_meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )


def _read_file_hash(path: Path,  max_file_bytes: int | None = None) -> str | None:
    try:
        if max_file_bytes is not None and path.stat().st_size > max_file_bytes:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _delete_path(conn: sqlite3.Connection, rel: str) -> None:
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
    conn.execute("DELETE FROM files WHERE path = ?", (rel,))


def _upsert_file_record(
    conn: sqlite3.Connection,
    rel: str,
    stat: os.stat_result,
    file_hash: str,
    chunks_count: int,
    now: int,
) -> None:
    conn.execute(
        """
        INSERT INTO files(path, size_bytes, mtime_ns, content_hash, chunks_count, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            size_bytes=excluded.size_bytes,
            mtime_ns=excluded.mtime_ns,
            content_hash=excluded.content_hash,
            chunks_count=excluded.chunks_count,
            indexed_at=excluded.indexed_at
        """,
        (rel, stat.st_size, stat.st_mtime_ns, file_hash, chunks_count, now),
    )


def _index_file(
    conn: sqlite3.Connection,
    repo_root: Path,
    path: Path,
    now: int,
    chunk_lines: int,
    chunk_chars: int,
    max_file_bytes: int | None = None,
) -> int:
    rel = path.relative_to(repo_root).as_posix()
    try:
        stat = path.stat()
    except OSError:
        return 0
    if max_file_bytes is not None and stat.st_size > max_file_bytes:
        return 0

    file_hash = _read_file_hash(path, max_file_bytes=max_file_bytes)
    if file_hash is None:
        return 0

    text = _read_text(path, max_file_bytes=max_file_bytes)
    _delete_path(conn, rel)

    if text is None or not text.strip():
        _upsert_file_record(conn, rel, stat, file_hash, 0, now)
        return 0

    kind = path.suffix.lower().lstrip(".") or "text"
    chunks_written = 0
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
        chunks_written += 1

    _upsert_file_record(conn, rel, stat, file_hash, chunks_written, now)
    return chunks_written


def _chunk_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return int(row[0] if row else 0)


def _file_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
    return int(row[0] if row else 0)


def build_index(
    repo_root: Path,
    db: Path,
    suffixes: set[str],
    exclude_dirs: set[str] | None,
    max_file_bytes: int,
    chunk_lines: int,
    chunk_chars: int,
    source: str = SOURCE_GIT_DEFAULT,
    mode: str = MODE_DELTA,
) -> dict[str, int | str]:
    repo_root = repo_root.resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise FileNotFoundError(f"repository root not found: {repo_root}")
    if source not in {SOURCE_GIT_DEFAULT, SOURCE_FILESYSTEM}:
        raise ValueError(f"unsupported source: {source}")
    if mode not in {MODE_DELTA, MODE_FULL}:
        raise ValueError(f"unsupported mode: {mode}")

    conn = _connect(db)
    now = int(time.time())
    candidate_paths = sorted(
        _iter_files(repo_root, suffixes, max_file_bytes, source),
        key=lambda item: item.relative_to(repo_root).as_posix(),
    )
    candidate_rels = {path.relative_to(repo_root).as_posix() for path in candidate_paths}
    files_reindexed = 0
    files_skipped = 0
    files_deleted = 0
    chunks_written = 0

    try:
        if mode == MODE_FULL:
            _init_schema(conn)
        else:
            _ensure_schema(conn)

        _upsert_meta(conn, "repo_root", str(repo_root))
        _upsert_meta(conn, "indexed_at", str(now))
        _upsert_meta(conn, "index_version", "2")
        _upsert_meta(conn, "index_source", source)
        _upsert_meta(conn, "index_mode", mode)
        _upsert_meta(conn, "selector", "git ls-files --cached --others --exclude-standard")

        old_chunk_paths = {row[0] for row in conn.execute("SELECT DISTINCT path FROM chunks")}
        old_file_paths = {row[0] for row in conn.execute("SELECT path FROM files")}
        stale_paths = (old_chunk_paths | old_file_paths) - candidate_rels
        for rel in sorted(stale_paths):
            _delete_path(conn, rel)
            files_deleted += 1

        for path in candidate_paths:
            rel = path.relative_to(repo_root).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > max_file_bytes:
                continue

            row = conn.execute(
                "SELECT size_bytes, mtime_ns, content_hash FROM files WHERE path = ?",
                (rel,),
            ).fetchone()
            if (
                mode == MODE_DELTA
                and row is not None
                and int(row[0]) == stat.st_size
                and int(row[1]) == stat.st_mtime_ns
            ):
                files_skipped += 1
                continue

            chunks_written += _index_file(
                conn,
                repo_root,
                path,
                now,
                chunk_lines,
                chunk_chars,
                max_file_bytes=max_file_bytes,
            )
            files_reindexed += 1

        conn.commit()
        files_indexed = _file_count(conn)
        chunks_indexed = _chunk_count(conn)
    finally:
        conn.close()

    return {
        "db": str(db),
        "repo_root": str(repo_root),
        "source": source,
        "mode": mode,
        "candidate_files": len(candidate_paths),
        "files_indexed": files_indexed,
        "chunks_indexed": chunks_indexed,
        "files_reindexed": files_reindexed,
        "files_skipped": files_skipped,
        "files_deleted": files_deleted,
        "chunks_written": chunks_written,
    }


def _parse_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Codex RAG SQLite/FTS5 index.")
    parser.add_argument("--repo", default=os.environ.get("AICARMINE_RAG_REPO") or os.environ.get("AICARMINE_LAB_REPO") or ".")
    parser.add_argument("--db", default=os.environ.get("AICARMINE_RAG_DB") or str(_default_db()))
    parser.add_argument("--suffixes", default=",".join(sorted(DEFAULT_SUFFIXES)))
    parser.add_argument("--exclude-dirs", default="", help=argparse.SUPPRESS)
    parser.add_argument("--source", choices=(SOURCE_GIT_DEFAULT, SOURCE_FILESYSTEM), default=os.environ.get("AICARMINE_RAG_INDEX_SOURCE") or SOURCE_GIT_DEFAULT)
    parser.add_argument("--mode", choices=(MODE_DELTA, MODE_FULL), default=os.environ.get("AICARMINE_RAG_INDEX_MODE") or MODE_DELTA)
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
        source=args.source,
        mode=args.mode,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
