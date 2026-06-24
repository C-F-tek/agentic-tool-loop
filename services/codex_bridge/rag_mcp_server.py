#!/usr/bin/env python3
"""
MCP server for Codex RAG context.

This server is intentionally separate from the general aicarmine_tools MCP
surface. It exposes direct RAG tools:

  aicarmine_rag_context
  aicarmine_rag_index_status
  aicarmine_rag_reindex

Search reads an explicit SQLite/FTS5 index and optionally reranks candidates
through the existing local OVMS reranker. Reindex writes only the RAG SQLite
index and never calls OpenWebUI, the broker, or the general repo dispatcher.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO

from rag_index_repo import (
    CHUNK_CHARS_DEFAULT,
    CHUNK_LINES_DEFAULT,
    DEFAULT_SUFFIXES,
    MAX_FILE_BYTES_DEFAULT,
    MODE_DELTA,
    MODE_FULL,
    SOURCE_FILESYSTEM,
    SOURCE_GIT_DEFAULT,
    build_index,
)
from repo_mcp_common import (
    err as _err_response,
)
from repo_mcp_common import (
    ok as _ok_response,
)
from repo_mcp_common import (
    safe_bool,
    safe_float,
    safe_int,
    tool_content,
)

SERVER_NAME = "aicarmine-codex-rag-mcp"
SERVER_VERSION = "1.2.0"
STDIO_TRANSPORT = os.environ.get("AICARMINE_RAG_MCP_STDIO_TRANSPORT", "").strip().lower()
DEBUG = os.environ.get("AICARMINE_RAG_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
DEFAULT_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_RERANK_TIMEOUT_SECONDS = 30.0
DEFAULT_RERANK_CANDIDATE_LIMIT = 12
DEFAULT_RERANK_DOC_CHARS = 2500


def _log(message: str) -> None:
    if DEBUG:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)




def _env_path(name: str, default: str = "") -> Path | None:
    value = os.environ.get(name, default).strip()
    return Path(value).expanduser() if value else None


def _default_db() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _db_path() -> Path:
    return _env_path("AICARMINE_RAG_DB") or _default_db()


def _repo_root(args: dict[str, Any] | None = None) -> Path:
    args = args or {}
    value = (
        str(args.get("repo") or "").strip()
        or os.environ.get("AICARMINE_RAG_REPO", "").strip()
        or os.environ.get("AICARMINE_LAB_REPO", "").strip()
        or os.getcwd()
    )
    return Path(value).expanduser()


def _parse_csv(value: Any, default: set[str]) -> set[str]:
    if value is None:
        return set(default)
    text = str(value).strip()
    if not text:
        return set(default)
    return {item.strip() for item in text.split(",") if item.strip()}


def _git_candidate_count(root: Path) -> dict[str, Any]:
    try:
        result = subprocess_run_git_candidate_count(root)
        return {"ok": True, **result}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def subprocess_run_git_candidate_count(root: Path) -> dict[str, Any]:
    import subprocess

    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git ls-files failed")
    files = [item for item in proc.stdout.split("\0") if item]
    return {
        "repo": str(root),
        "selector": "git ls-files --cached --others --exclude-standard",
        "candidate_files": len(files),
    }


def _connect_readonly(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _read_message(stdin: BinaryIO) -> dict[str, Any] | None:
    global STDIO_TRANSPORT

    while True:
        first = stdin.readline()
        if not first:
            return None
        decoded = first.decode("utf-8-sig", errors="replace").strip()
        if decoded:
            break

    if decoded.startswith("{"):
        if not STDIO_TRANSPORT:
            STDIO_TRANSPORT = "jsonl"
        return json.loads(decoded)

    headers: dict[str, str] = {}
    if ":" in decoded:
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    while True:
        line = stdin.readline()
        if not line:
            return None
        decoded = line.decode("utf-8", errors="replace").strip()
        if decoded == "":
            break
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    try:
        length = int(headers.get("content-length", "0"))
    except ValueError:
        return None
    if length <= 0:
        return None

    body = stdin.read(length)
    if not body:
        return None

    if not STDIO_TRANSPORT:
        STDIO_TRANSPORT = "content-length"
    return json.loads(body.decode("utf-8-sig", errors="replace"))


def _write_message(stdout: BinaryIO, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if STDIO_TRANSPORT == "content-length":
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
    else:
        stdout.write(raw + b"\n")
    stdout.flush()


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 20) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read()
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            return {"status": getattr(res, "status", None)}
        if "application/json" in (res.headers.get("Content-Type") or "").lower() or text.strip().startswith(("{", "[")):
            return json.loads(text)
        return {"status": getattr(res, "status", None), "text": text[:2000]}


def _reranker_ready() -> dict[str, Any]:
    url = os.environ.get("AICARMINE_RAG_RERANK_READY_URL", DEFAULT_READY_URL).strip() or DEFAULT_READY_URL
    try:
        value = _http_json("GET", url, timeout=10)
        return {"ok": True, "url": url, "result": value}
    except Exception as exc:
        return {"ok": False, "url": url, "error": type(exc).__name__, "detail": str(exc)}


def _db_inspect(db: Path) -> dict[str, Any]:
    if not db.exists():
        return {"ok": False, "db": str(db), "error": "db_not_found"}

    conn = _connect_readonly(db)
    try:
        tables = []
        for row in conn.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        ):
            name = row["name"]
            cols = [dict(c) for c in conn.execute(f'PRAGMA table_info("{name}")')]
            count = None
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except Exception:
                pass
            tables.append(
                {
                    "name": name,
                    "type": row["type"],
                    "is_fts": bool(row["sql"] and "VIRTUAL TABLE" in row["sql"].upper() and "FTS" in row["sql"].upper()),
                    "columns": [c.get("name") for c in cols],
                    "rows": count,
                }
            )

        meta = {}
        try:
            for row in conn.execute("SELECT key, value FROM index_meta"):
                meta[str(row["key"])] = str(row["value"])
        except Exception:
            pass

        return {"ok": True, "db": str(db), "meta": meta, "tables": tables}
    finally:
        conn.close()


def _git_head(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _safe_rag_metadata(repo: Path, db: Path, db_status: dict[str, Any]) -> dict[str, Any]:
    meta = db_status.get("meta") if isinstance(db_status.get("meta"), dict) else {}
    current_commit = _git_head(repo)
    indexed_commit = str(
        meta.get("indexed_commit")
        or meta.get("git_commit")
        or meta.get("commit")
        or ""
    ).strip()
    indexed_repo_root = str(meta.get("repo_root") or "").strip()
    stale_reasons: list[str] = []
    if indexed_commit and current_commit and indexed_commit != current_commit:
        stale_reasons.append("commit_mismatch")
    if indexed_repo_root:
        try:
            if Path(indexed_repo_root).resolve(strict=False) != repo.resolve(strict=False):
                stale_reasons.append("repo_root_mismatch")
        except Exception:
            stale_reasons.append("repo_root_unresolved")
    return {
        "repo_root": str(repo),
        "db_path": str(db),
        "indexed_repo_root": indexed_repo_root,
        "current_commit": current_commit,
        "indexed_commit": indexed_commit,
        "indexed_at": str(meta.get("indexed_at") or ""),
        "stale_determinable": bool(indexed_commit or indexed_repo_root),
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
    }


def _fts_query(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_./:-]{2,}", text)
    tokens = [token[:96].replace('"', '""') for token in tokens][:40]
    if not tokens:
        return '""'
    quoted = [f'"{token}"' for token in tokens]
    if len(quoted) <= 4:
        return " AND ".join(quoted)
    return " OR ".join(quoted)


def _fallback_like_query(conn: sqlite3.Connection, query: str, candidate_limit: int) -> list[dict[str, Any]]:
    like = f"%{query[:200]}%"
    rows = conn.execute(
        """
        SELECT id, path, start_line, end_line, symbol, kind, content, 0.0 AS rank
        FROM chunks
        WHERE content LIKE ? OR path LIKE ? OR symbol LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, like, candidate_limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _fts_candidates(conn: sqlite3.Connection, query: str, candidate_limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    match = _fts_query(query)

    try:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.path,
                c.start_line,
                c.end_line,
                c.symbol,
                c.kind,
                c.content,
                bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks AS c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, candidate_limit),
        ).fetchall()
        return [dict(row) for row in rows], warnings
    except Exception as exc:
        warnings.append(f"fts_match_failed:{type(exc).__name__}:{exc}")
        return _fallback_like_query(conn, query, candidate_limit), warnings


def _parse_rerank_results(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw_results = value.get("results") or value.get("data") or []
    elif isinstance(value, list):
        raw_results = value
    else:
        raw_results = []

    out: list[dict[str, Any]] = []
    for position, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        index = item.get("index", item.get("document_index", item.get("id", position)))
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = position
        score = item.get("relevance_score", item.get("score", item.get("logit", 0.0)))
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
        out.append({"index": idx, "score": score_value, "raw": item})
    return out


def _rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    enabled: bool,
    candidate_limit: int,
    doc_chars: int,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    started = time.monotonic()
    effective_timeout = safe_float(timeout_seconds, DEFAULT_RERANK_TIMEOUT_SECONDS, low=1.0, high=60.0)
    url = os.environ.get("AICARMINE_RAG_RERANK_URL", DEFAULT_RERANK_URL).strip() or DEFAULT_RERANK_URL
    model = os.environ.get("AICARMINE_RAG_RERANK_MODEL", DEFAULT_RERANK_MODEL).strip() or DEFAULT_RERANK_MODEL
    meta: dict[str, Any] = {
        "enabled": bool(enabled),
        "status": "not_started",
        "url": url,
        "model": model,
        "candidate_limit": candidate_limit,
        "doc_chars": doc_chars,
        "timeout_requested": timeout_seconds,
        "timeout_seconds": effective_timeout,
    }

    if not enabled:
        meta["status"] = "skipped_disabled"
        return candidates, warnings, meta

    rerank_candidates = candidates[:candidate_limit]
    docs = [str(item.get("content") or "")[:doc_chars] for item in rerank_candidates]
    meta["input_count"] = len(docs)

    if not docs:
        meta["status"] = "skipped_no_candidates"
        return [], warnings, meta

    payload = {"model": model, "query": query, "documents": docs}

    try:
        response = _http_json("POST", url, payload=payload, timeout=max(1, int(effective_timeout)))
        parsed = _parse_rerank_results(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        warnings.append(f"reranker_unavailable:{type(exc).__name__}:{exc}")
        meta.update(
            {
                "status": "unavailable",
                "error": type(exc).__name__,
                "detail": str(exc),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
        ranked = []
        for candidate in candidates:
            merged = dict(candidate)
            merged["rerank_score"] = None
            ranked.append(merged)
        return ranked, warnings, meta

    if not isinstance(response, (dict, list)):
        warnings.append(f"reranker_invalid_response:{type(response).__name__}")
        ranked = []
        for candidate in candidates:
            merged = dict(candidate)
            merged["rerank_score"] = None
            ranked.append(merged)
        meta.update(
            {
                "status": "invalid_response",
                "error": "reranker_response_not_json_shape",
                "response_type": type(response).__name__,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
        return ranked, warnings, meta

    if not parsed:
        warnings.append("reranker_no_scores")
        ranked = []
        for candidate in candidates:
            merged = dict(candidate)
            merged["rerank_score"] = None
            ranked.append(merged)
        meta.update(
            {
                "status": "no_scores",
                "returned_scores": 0,
                "ranked_count": len(ranked),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
        return ranked, warnings, meta

    ranked: list[dict[str, Any]] = []
    seen: set[int] = set()

    for item in parsed:
        idx = item["index"]
        if idx < 0 or idx >= len(rerank_candidates) or idx in seen:
            continue
        seen.add(idx)
        merged = dict(rerank_candidates[idx])
        merged["rerank_score"] = item["score"]
        ranked.append(merged)

    for idx, candidate in enumerate(rerank_candidates):
        if idx in seen:
            continue
        merged = dict(candidate)
        merged["rerank_score"] = None
        ranked.append(merged)

    for candidate in candidates[candidate_limit:]:
        merged = dict(candidate)
        merged["rerank_score"] = None
        ranked.append(merged)

    meta.update(
        {
            "status": "ready",
            "returned_scores": len(parsed),
            "ranked_count": len(ranked),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
    )
    return ranked, warnings, meta


def _env_int(name: str, default: int, *, low: int, high: int) -> int:
    return safe_int(os.environ.get(name), default, low=low, high=high)


def _env_float(name: str, default: float, *, low: float, high: float) -> float:
    return safe_float(os.environ.get(name), default, low=low, high=high)


def _search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing query"}

    db = Path(args.get("db") or _db_path()).expanduser()
    candidate_limit = safe_int(args.get("candidate_limit"), 80, low=1, high=300)
    top_k = safe_int(args.get("top_k"), 12, low=1, high=50)
    max_chunk_chars = safe_int(args.get("max_chunk_chars"), 4000, low=400, high=20000)
    rerank_enabled = safe_bool(args.get("rerank"), default=True)
    rerank_candidate_limit = safe_int(
        args.get("rerank_candidate_limit"),
        _env_int("AICARMINE_RAG_RERANK_CANDIDATE_LIMIT", DEFAULT_RERANK_CANDIDATE_LIMIT, low=1, high=100),
        low=1,
        high=min(100, candidate_limit),
    )
    rerank_doc_chars = safe_int(
        args.get("rerank_doc_chars"),
        _env_int("AICARMINE_RAG_RERANK_DOC_CHARS", DEFAULT_RERANK_DOC_CHARS, low=200, high=20000),
        low=200,
        high=20000,
    )
    rerank_timeout_seconds = safe_float(
        args.get("rerank_timeout_seconds"),
        _env_float("AICARMINE_RAG_RERANK_TIMEOUT_SECONDS", DEFAULT_RERANK_TIMEOUT_SECONDS, low=1.0, high=120.0),
        low=1.0,
        high=120.0,
    )
    max_total_chars = safe_int(
        args.get("max_total_chars") or os.environ.get("AICARMINE_RAG_MAX_TOTAL_CHARS"),
        50_000,
        low=1000,
        high=200_000,
    )

    if not db.exists():
        return {"ok": False, "error": "db_not_found", "db": str(db)}

    conn = _connect_readonly(db)
    try:
        candidates, warnings = _fts_candidates(conn, query, candidate_limit)
    finally:
        conn.close()

    ranked, rerank_warnings, rerank = _rerank(
        query,
        candidates,
        enabled=rerank_enabled,
        candidate_limit=rerank_candidate_limit,
        doc_chars=rerank_doc_chars,
        timeout_seconds=rerank_timeout_seconds,
    )
    warnings.extend(rerank_warnings)

    chunks = []
    used_chars = 0

    for rank, item in enumerate(ranked[:top_k], start=1):
        content = str(item.get("content") or "")
        remaining_chars = max_total_chars - used_chars
        if remaining_chars <= 0:
            break
        chunk_limit = min(max_chunk_chars, remaining_chars)
        if len(content) > chunk_limit:
            suffix = "\n...[chunk truncated]"
            if chunk_limit > len(suffix):
                content = content[: chunk_limit - len(suffix)].rstrip() + suffix
            else:
                content = content[:chunk_limit]
        used_chars += len(content)

        chunks.append(
            {
                "rank": rank,
                "score": item.get("rerank_score"),
                "fts_rank": item.get("rank"),
                "path": item.get("path"),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
                "symbol": item.get("symbol"),
                "kind": item.get("kind"),
                "content": content,
            }
        )

    return {
        "ok": True,
        "tool": "aicarmine_rag_context",
        "operation": "search",
        "db": str(db),
        "query": query,
        "candidate_count": len(candidates),
        "returned": len(chunks),
        "used_chars": used_chars,
        "rerank": rerank,
        "chunks": chunks,
        "warnings": warnings,
    }


def _index_status(args: dict[str, Any]) -> dict[str, Any]:
    db = Path(args.get("db") or _db_path()).expanduser()
    repo = _repo_root(args).resolve()
    status = _db_inspect(db)
    rag_metadata = _safe_rag_metadata(repo, db, status)
    return {
        "ok": bool(status.get("ok")),
        "tool": "aicarmine_rag_index_status",
        "db": str(db),
        "repo_root": str(repo),
        "rag_metadata": rag_metadata,
        "current_commit": rag_metadata.get("current_commit", ""),
        "indexed_commit": rag_metadata.get("indexed_commit", ""),
        "stale": rag_metadata.get("stale", False),
        "db_status": status,
        "git_surface": _git_candidate_count(repo),
        "defaults": {
            "source": SOURCE_GIT_DEFAULT,
            "mode": MODE_DELTA,
            "selector": "git ls-files --cached --others --exclude-standard",
            "max_file_bytes": MAX_FILE_BYTES_DEFAULT,
            "chunk_lines": CHUNK_LINES_DEFAULT,
            "chunk_chars": CHUNK_CHARS_DEFAULT,
        },
        "reranker": _reranker_ready(),
    }


def _reindex(args: dict[str, Any]) -> dict[str, Any]:
    db = Path(args.get("db") or _db_path()).expanduser()
    repo = _repo_root(args).resolve()
    source = str(args.get("source") or os.environ.get("AICARMINE_RAG_INDEX_SOURCE") or SOURCE_GIT_DEFAULT).strip().lower()
    mode = str(args.get("mode") or os.environ.get("AICARMINE_RAG_INDEX_MODE") or MODE_DELTA).strip().lower()
    suffixes = _parse_csv(args.get("suffixes"), DEFAULT_SUFFIXES)
    max_file_bytes = safe_int(args.get("max_file_bytes"), MAX_FILE_BYTES_DEFAULT, low=1, high=100_000_000)
    chunk_lines = safe_int(args.get("chunk_lines"), CHUNK_LINES_DEFAULT, low=20, high=2000)
    chunk_chars = safe_int(args.get("chunk_chars"), CHUNK_CHARS_DEFAULT, low=1000, high=200_000)

    if source not in {SOURCE_GIT_DEFAULT, SOURCE_FILESYSTEM}:
        return {"ok": False, "error": f"unsupported source: {source}"}
    if mode not in {MODE_DELTA, MODE_FULL}:
        return {"ok": False, "error": f"unsupported mode: {mode}"}

    result = build_index(
        repo_root=repo,
        db=db,
        suffixes=suffixes,
        exclude_dirs=set(),
        max_file_bytes=max_file_bytes,
        chunk_lines=chunk_lines,
        chunk_chars=chunk_chars,
        source=source,
        mode=mode,
    )
    return {
        "ok": True,
        "tool": "aicarmine_rag_reindex",
        "selector": "git ls-files --cached --others --exclude-standard" if source == SOURCE_GIT_DEFAULT else "filesystem",
        "result": result,
    }


def _handle_context_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "search").strip().lower()
    db = Path(arguments.get("db") or _db_path()).expanduser()

    if operation == "health":
        inspect_result = _db_inspect(db)
        repo = _repo_root(arguments).resolve()
        rag_metadata = _safe_rag_metadata(repo, db, inspect_result)
        return tool_content(
            {
                "ok": bool(inspect_result.get("ok")),
                "db": str(db),
                "repo_root": str(repo),
                "rag_metadata": rag_metadata,
                "current_commit": rag_metadata.get("current_commit", ""),
                "indexed_commit": rag_metadata.get("indexed_commit", ""),
                "stale": rag_metadata.get("stale", False),
                "db_status": inspect_result,
                "reranker": _reranker_ready(),
            }
        )

    if operation == "inspect":
        return tool_content(_db_inspect(db))

    if operation == "search":
        return tool_content(_search(arguments))

    return tool_content({"ok": False, "error": f"unknown operation: {operation}"}, is_error=True)


def _handle_status_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    return tool_content(_index_status(arguments))


def _handle_reindex_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    result = _reindex(arguments)
    return tool_content(result, is_error=not bool(result.get("ok")))


TOOL_SCHEMAS = [
    {
        "name": "aicarmine_rag_context",
        "description": "Search the Codex RAG SQLite/FTS5 index and optionally rerank candidates with the local BGE reranker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "db": {"type": "string"},
                "candidate_limit": {"type": "integer", "default": 80},
                "top_k": {"type": "integer", "default": 12},
                "max_chunk_chars": {"type": "integer", "default": 4000},
                "max_total_chars": {"type": "integer", "default": 50000},
                "rerank": {"type": "boolean", "default": True},
                "rerank_candidate_limit": {"type": "integer", "default": DEFAULT_RERANK_CANDIDATE_LIMIT},
                "rerank_doc_chars": {"type": "integer", "default": DEFAULT_RERANK_DOC_CHARS},
                "rerank_timeout_seconds": {"type": "number", "default": DEFAULT_RERANK_TIMEOUT_SECONDS},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "aicarmine_rag_index_status",
        "description": "Inspect the Codex RAG index, DB metadata, Git/.gitignore candidate surface, and reranker readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "db": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "aicarmine_rag_reindex",
        "description": "Update the Codex RAG SQLite index. Default mode is delta over Git candidates: tracked plus untracked files not excluded by .gitignore.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "db": {"type": "string"},
                "source": {"type": "string", "enum": [SOURCE_GIT_DEFAULT, SOURCE_FILESYSTEM], "default": SOURCE_GIT_DEFAULT},
                "mode": {"type": "string", "enum": [MODE_DELTA, MODE_FULL], "default": MODE_DELTA},
                "suffixes": {"type": "string"},
                "max_file_bytes": {"type": "integer", "default": MAX_FILE_BYTES_DEFAULT},
                "chunk_lines": {"type": "integer", "default": CHUNK_LINES_DEFAULT},
                "chunk_chars": {"type": "integer", "default": CHUNK_CHARS_DEFAULT},
            },
            "additionalProperties": True,
        },
    },
]

INSTRUCTIONS = (
    "AI-Carmine RAG MCP. Use aicarmine_rag_context for codebase retrieval, "
    "aicarmine_rag_index_status to inspect index freshness, and "
    "aicarmine_rag_reindex to update the SQLite index from the Git/.gitignore "
    "candidate surface."
)


def _handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if msg_id is None and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            return _ok_response(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": INSTRUCTIONS,
                },
            )

        if method == "ping":
            return _ok_response(msg_id, {})

        if method == "tools/list":
            return _ok_response(msg_id, {"tools": TOOL_SCHEMAS})

        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            handlers = {
                "aicarmine_rag_context": _handle_context_tool,
                "aicarmine_rag_index_status": _handle_status_tool,
                "aicarmine_rag_reindex": _handle_reindex_tool,
            }
            handler = handlers.get(name)
            if handler is None:
                return _ok_response(msg_id, tool_content({"ok": False, "error": f"unknown tool: {name}"}, is_error=True))
            return _ok_response(msg_id, handler(arguments))

        return _err_response(msg_id, -32601, f"method not found: {method}")
    except Exception as exc:
        _log(traceback.format_exc())
        return _ok_response(msg_id, tool_content({"ok": False, "error": type(exc).__name__, "detail": str(exc)}, is_error=True))


def main() -> int:
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return 0
        response = _handle_rpc(message)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


if __name__ == "__main__":
    raise SystemExit(main())
