#!/usr/bin/env python3
"""
Single-tool MCP server for Codex RAG context.

This server is intentionally separate from the general aicarmine_tools MCP
surface. It exposes exactly one read-only tool:

  aicarmine_rag_context

The tool reads an explicit SQLite/FTS5 index and optionally reranks candidates
through the existing local OVMS reranker. It does not import OpenWebUI, the
broker, or the general repo dispatcher, and it never writes files.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import git
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO


# --- MCP roots support ---
CLIENT_SUPPORTS_ROOTS = False
SERVER_REQUEST_ID = 100000

SERVER_NAME = "aicarmine-codex-rag-mcp"
SERVER_VERSION = "1.1.0"
STDIO_TRANSPORT = os.environ.get("AICARMINE_RAG_MCP_STDIO_TRANSPORT", "").strip().lower()
DEBUG = os.environ.get("AICARMINE_RAG_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
DEFAULT_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def _log(message: str) -> None:
    if DEBUG:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json_dumps(value)}], "isError": is_error}


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _safe_int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def _env_path(name: str, default: str = "") -> Path | None:
    value = os.environ.get(name, default).strip()
    return Path(value).expanduser() if value else None


def _default_db() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _db_path() -> Path:
    return _env_path("AICARMINE_RAG_DB") or _default_db()


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


def _rerank(query: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    url = os.environ.get("AICARMINE_RAG_RERANK_URL", DEFAULT_RERANK_URL).strip() or DEFAULT_RERANK_URL
    model = os.environ.get("AICARMINE_RAG_RERANK_MODEL", DEFAULT_RERANK_MODEL).strip() or DEFAULT_RERANK_MODEL
    docs = [str(item.get("content") or "") for item in candidates]

    if not docs:
        return [], warnings

    payload = {"model": model, "query": query, "documents": docs}

    try:
        response = _http_json("POST", url, payload=payload, timeout=30)
        parsed = _parse_rerank_results(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        warnings.append(f"reranker_unavailable:{type(exc).__name__}:{exc}")
        parsed = [{"index": idx, "score": -float(idx), "raw": {}} for idx, _ in enumerate(candidates)]

    ranked: list[dict[str, Any]] = []
    seen: set[int] = set()

    for item in parsed:
        idx = item["index"]
        if idx < 0 or idx >= len(candidates) or idx in seen:
            continue
        seen.add(idx)
        merged = dict(candidates[idx])
        merged["rerank_score"] = item["score"]
        ranked.append(merged)

    for idx, candidate in enumerate(candidates):
        if idx in seen:
            continue
        merged = dict(candidate)
        merged["rerank_score"] = None
        ranked.append(merged)

    return ranked, warnings


def _search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing query"}

    db = Path(args.get("db") or _db_path()).expanduser()
    candidate_limit = _safe_int(args.get("candidate_limit"), 80, low=1, high=300)
    top_k = _safe_int(args.get("top_k"), 12, low=1, high=50)
    max_chunk_chars = _safe_int(args.get("max_chunk_chars"), 4000, low=400, high=20000)
    max_total_chars = _safe_int(
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

    ranked, rerank_warnings = _rerank(query, candidates)
    warnings.extend(rerank_warnings)

    chunks = []
    used_chars = 0

    for rank, item in enumerate(ranked[:top_k], start=1):
        content = str(item.get("content") or "")
        if len(content) > max_chunk_chars:
            content = content[:max_chunk_chars].rstrip() + "\n...[chunk truncated]"
        if used_chars + len(content) > max_total_chars:
            break
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
        "chunks": chunks,
        "warnings": warnings,
    }



def _ensure_db_schema(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {str(r['name']) for r in tables}
        if 'chunks' not in table_names:
            conn.execute(
                "CREATE TABLE chunks (id INTEGER PRIMARY KEY, repo_root TEXT NOT NULL, path TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, symbol TEXT, kind TEXT, content TEXT NOT NULL, content_hash TEXT NOT NULL, updated_at INTEGER NOT NULL)"
            )
            conn.execute("CREATE INDEX idx_chunks_path ON chunks(path)")
            conn.execute("CREATE INDEX idx_chunks_hash ON chunks(content_hash)")
            conn.execute(
                "CREATE VIRTUAL TABLE chunks_fts USING fts5(path, symbol, kind, content, content='chunks', content_rowid='id', tokenize='unicode61')"
            )
            conn.execute(
                "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid, path, symbol, kind, content) VALUES (new.id, new.path, new.symbol, new.kind, new.content); END;"
            )
            conn.execute(
                "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content) VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content); END;"
            )
            conn.execute(
                "CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts, rowid, path, symbol, kind, content) VALUES ('delete', old.id, old.path, old.symbol, old.kind, old.content); INSERT INTO chunks_fts(rowid, path, symbol, kind, content) VALUES (new.id, new.path, new.symbol, new.kind, new.content); END;"
            )
            conn.execute("CREATE TABLE IF NOT EXISTS index_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    finally:
        conn.close()


def _next_server_request_id() -> int:
    global SERVER_REQUEST_ID
    SERVER_REQUEST_ID += 1
    return SERVER_REQUEST_ID


def _request_client_roots() -> list:
    if not CLIENT_SUPPORTS_ROOTS:
        raise RuntimeError('Codex MCP client did not advertise roots capability')
    request_id = _next_server_request_id()
    request = {'jsonrpc': '2.0', 'id': request_id, 'method': 'roots/list', 'params': {}}
    _write_message(sys.stdout.buffer, request)
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            raise RuntimeError('Codex MCP client closed before roots/list response')
        if message.get('id') == request_id:
            if 'error' in message:
                raise RuntimeError('roots/list failed: ' + str(message['error']))
            result = message.get('result') if isinstance(message.get('result'), dict) else {}
            roots = result.get('roots') if isinstance(result.get('roots'), list) else []
            return [root for root in roots if isinstance(root, dict)]
        response = _handle_rpc(message)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


def _path_from_file_uri(uri):
    if not uri.startswith('file://'):
        raise RuntimeError('unsupported root uri: ' + uri)
    raw = uri[7:]
    if raw.startswith('/') and len(raw) >= 4 and raw[2] == ':':
        raw = raw[1:]
    return Path(raw).expanduser().resolve()


def _git_root(candidate):
    current = candidate.resolve()
    if current.is_file():
        current = current.parent
    for item in [current] + list(current.parents):
        if (item / '.git').exists():
            return item
    raise RuntimeError('MCP root is not inside a git repository: ' + str(candidate))


def _codex_app_repo_root():
    roots = _request_client_roots()
    if not roots:
        raise RuntimeError('Codex MCP client returned no roots')
    if len(roots) != 1:
        raise RuntimeError('Codex MCP client returned multiple roots: ' + str(roots))
    uri = str(roots[0].get('uri') or '')
    if not uri:
        raise RuntimeError('Codex MCP root has no uri: ' + str(roots[0]))
    return _git_root(_path_from_file_uri(uri))


def _read_text_file(path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b'\x00' in data[:4096]:
        return None
    for enc in ('utf-8', 'utf-8-sig', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def _guess_symbol(line_list):
    for line in line_list:
        s = line.strip()
        if s.startswith('def ') or s.startswith('async def '):
            return s.split(':', 1)[0][:240]
        if s.startswith('class '):
            return s.split(':', 1)[0][:240]
        if s.startswith('function '):
            return s.split('{', 1)[0][:240]
    return ''


def _chunk_lines(text, max_lines, max_chars):
    lines_t = text.splitlines()
    start = 0
    result = []
    while start < len(lines_t):
        end = min(len(lines_t), start + max_lines)
        chunk = chr(10).join(lines_t[start:end]).strip()
        while len(chunk) > max_chars and end - start > 20:
            end = start + max(20, (end - start) // 2)
            chunk = chr(10).join(lines_t[start:end]).strip()
        if chunk:
            result.append((start + 1, end, chunk))
        start = end
    return result


def _delta_reindex(repo_path, db, since):
    repo = git.Repo(str(repo_path))
    repo_root = repo.working_dir
    import time, hashlib
    now = int(time.time())
    file_count = 0
    changed_files = []
    removed_files = []

    if since:
        try:
            diff_output = repo.git.diff(since, name_status=True).strip()
            for line in diff_output.splitlines():
                parts = line.split(chr(9))
                if len(parts) >= 2:
                    status_code = parts[0]
                    fpath = parts[-1]
                    if status_code != 'D':
                        changed_files.append(fpath)
                    else:
                        removed_files.append(fpath)
        except Exception:
            diff_output = repo.git.diff(name_status=True).strip()
            for line in diff_output.splitlines():
                parts = line.split(chr(9))
                if len(parts) >= 2:
                    changed_files.append(parts[-1])

    else:
        # Full reindex: all tracked files
        ls_output = repo.git.ls_files(z=True).strip()
        if ls_output:
            for f in ls_output.replace(chr(0), chr(10)).strip().split(chr(10)):
                if f:
                    changed_files.append(f)

    untracked = repo.git.ls_files(z=True, others=True, exclude_standard=True)
    if untracked:
        tracked_set = set(changed_files)
        for f in untracked.replace(chr(0), chr(10)).strip().split(chr(10)):
            if f and f not in tracked_set:
                changed_files.append(f)

    changed_files = list(dict.fromkeys(changed_files))
    removed_files = list(dict.fromkeys(removed_files))

    if removed_files:
        conn = sqlite3.connect(str(db))
        placeholders = ','.join('?' for _ in removed_files)
        conn.execute('DELETE FROM chunks WHERE path IN (' + placeholders + ')', removed_files)
        conn.commit()
        conn.close()

    allowed_suffixes = {'.py','.pyi','.ps1','.md','.toml','.yaml','.yml','.json','.txt','.ini','.cfg','.env','.sh','.bat','.cmd'}
    for rel_path in changed_files:
        full_path = Path(repo_root) / rel_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.stat().st_size > 2000000:
            continue
        suffix = full_path.suffix.lower()
        if suffix not in allowed_suffixes:
            continue
        text = _read_text_file(full_path)
        if text is None or not text.strip():
            continue
        kind = suffix.lower().lstrip('.') or 'text'
        conn = sqlite3.connect(str(db))
        # Always DELETE old chunks for this file, then re-insert fresh chunks.
        conn.execute('DELETE FROM chunks WHERE path = ?', (rel_path,))
        for start_line, end_line, chunk_content in _chunk_lines(text, 180, 12000):
            digest = hashlib.sha256(chunk_content.encode('utf-8', errors='replace')).hexdigest()
            symbol = _guess_symbol(chunk_content.splitlines()[:80])
            conn.execute('INSERT INTO chunks (repo_root, path, start_line, end_line, symbol, kind, content, content_hash, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (str(repo_root), rel_path, start_line, end_line, symbol, kind, chunk_content, digest, now))
        conn.commit()
        file_count += 1
        conn.close()

    conn = sqlite3.connect(str(db))
    conn.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)", ('repo_root', str(repo_root)))
    conn.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)", ('indexed_at', str(now)))
    conn.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)", ('last_delta_since', str(since)))
    conn.commit()
    conn.close()

    return {'ok': True, 'operation': 'reindex', 'db': str(db), 'repo_root': str(repo_root), 'delta_mode': True, 'since': since, 'changed_files': len(changed_files), 'removed_files': len(removed_files), 'files_indexed': file_count, 'indexed_at': now}

def _handle_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "search").strip().lower()
    db = Path(arguments.get("db") or _db_path()).expanduser()

    if operation == "health":
        inspect_result = _db_inspect(db)
        return _tool_content({"ok": bool(inspect_result.get("ok")), "db": str(db), "db_status": inspect_result, "reranker": _reranker_ready()})

    if operation == "inspect":
        return _tool_content(_db_inspect(db))

    if operation == "search":
        return _tool_content(_search(arguments))

    if operation == "reindex":
        repo_arg = arguments.get("repo")
        if repo_arg:
            repo_path = Path(repo_arg).expanduser()
        else:
            try:
                repo_path = _codex_app_repo_root()
            except RuntimeError as exc:
                return _tool_content({
                    "ok": False, "operation": "reindex",
                    "error": str(exc),
                    "hint": "Pass repo parameter or start from a Codex session with MCP roots.",
                }, is_error=True)
        since = arguments.get("since")
        _ensure_db_schema(db)
        try:
            result = _delta_reindex(repo_path, db, since)
            return _tool_content(result)
        except Exception as exc:
            return _tool_content({
                "ok": False, "operation": "reindex",
                "error": type(exc).__name__,
                "detail": str(exc),
            }, is_error=True)

    return _tool_content({"ok": False, "error": f"unknown operation: {operation}"}, is_error=True)


TOOL_SCHEMAS = [
    {
        "name": "aicarmine_rag_context",
        "description": "Read-only single-tool RAG lookup: SQLite/FTS5 candidates plus optional local OVMS rerank.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "default": "search"},
                "query": {"type": "string"},
                "db": {"type": "string"},
                "candidate_limit": {"type": "integer", "default": 80},
                "top_k": {"type": "integer", "default": 12},
                "max_chunk_chars": {"type": "integer", "default": 4000},
                "max_total_chars": {"type": "integer", "default": 50000},
            },
            "repo": {"type": "string", "description": "Override repo root for reindex; defaults to MCP roots if not provided."},
            "since": {"type": "string", "description": "Git commit ref or branch for delta reindex; defaults to HEAD."},
        },
    }
]

INSTRUCTIONS = (
    "AI-Carmine single-purpose RAG MCP. Exposes exactly one read-only tool: "
    "aicarmine_rag_context. Use it for codebase retrieval only; use other MCP "
    "servers for file reads, edits, validation, or commands. "
    "Operations: search (default), inspect, health, reindex."
)


def _handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if msg_id is None and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            global CLIENT_SUPPORTS_ROOTS
            capabilities = params.get("capabilities") if isinstance(params.get("capabilities"), dict) else {}
            CLIENT_SUPPORTS_ROOTS = isinstance(capabilities.get("roots"), dict)
            server_roots_caps = {}
            if CLIENT_SUPPORTS_ROOTS:
                server_roots_caps["roots"] = {"listChanged": False}
            return _ok(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "roots": server_roots_caps,
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": INSTRUCTIONS,
                },
            )

        if method == "ping":
            return _ok(msg_id, {})

        if method == "tools/list":
            return _ok(msg_id, {"tools": TOOL_SCHEMAS})

        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if name != "aicarmine_rag_context":
                return _ok(msg_id, _tool_content({"ok": False, "error": f"unknown tool: {name}"}, is_error=True))
            return _ok(msg_id, _handle_tool(arguments))

        return _err(msg_id, -32601, f"method not found: {method}")
    except Exception as exc:
        _log(traceback.format_exc())
        return _ok(msg_id, _tool_content({"ok": False, "error": type(exc).__name__, "detail": str(exc)}, is_error=True))


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