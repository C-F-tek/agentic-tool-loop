#!/usr/bin/env python3
"""Runtime SQLite memory MCP server - read/write SQLite memory for agentic loops."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO


SERVER_NAME = "aicarmine-runtime-sqlite-memory-mcp"
SERVER_VERSION = "0.1.0"
DEFAULT_DB = os.environ.get("AICARMINE_RUNTIME_SQLITE_MEMORY_DB", str(Path.home() / ".aicarmine" / "runtime_sqlite_memory.sqlite"))


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def number_prop(default: float, minimum: float, maximum: float) -> dict[str, Any]:
    return {"type": "number", "default": default, "minimum": minimum, "maximum": maximum}


def object_prop() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _safe_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _db_path() -> str:
    db = os.environ.get("AICARMINE_RUNTIME_SQLITE_MEMORY_DB", DEFAULT_DB)
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    return db


def _connect() -> "sqlite3.Connection":
    import sqlite3
    db = _db_path()
    conn = sqlite3.connect(db, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: "sqlite3.Connection") -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runtime_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT 'note',
            content TEXT NOT NULL,
            summary TEXT,
            scope TEXT NOT NULL DEFAULT 'project',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_memory_kind ON runtime_memory(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_memory_scope ON runtime_memory(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_memory_tags ON runtime_memory(tags)")
    conn.commit()


def _compute_checksum(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Read SQLite memory entry."""
    kind = args.get("kind", "note").strip() or "note"
    scope = args.get("scope", "project").strip() or "project"
    limit = _safe_int(args.get("limit", 50), 1, 1, 500)

    try:
        conn = _connect()
        _init_db(conn)
        rows = conn.execute(
            "SELECT id, kind, content, summary, scope, tags, created_at, updated_at, checksum FROM runtime_memory WHERE kind=? AND scope=? ORDER BY updated_at DESC LIMIT ?",
            (kind, scope, limit),
        ).fetchall()

        return {
            "ok": True,
            "count": len(rows),
            "entries": [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "scope": row["scope"],
                    "tags": row["tags"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "checksum": row["checksum"],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


def _write_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Write SQLite memory entry."""
    content = args.get("content", "").strip()
    kind = args.get("kind", "note").strip() or "note"
    summary = args.get("summary", "").strip() or None
    scope = args.get("scope", "project").strip() or "project"
    tags = args.get("tags", [])

    if not content:
        return {"ok": False, "error": "content_required", "error_type": "ValidationError"}

    try:
        conn = _connect()
        _init_db(conn)
        checksum = _compute_checksum(content)
        now = _now_iso()
        tags_json = json.dumps(tags, ensure_ascii=False)

        conn.execute(
            "INSERT INTO runtime_memory (kind, content, summary, scope, tags, created_at, updated_at, checksum) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, content, summary, scope, tags_json, now, now, checksum),
        )

        conn.commit()
        return {
            "ok": True,
            "kind": kind,
            "scope": scope,
            "checksum": checksum,
            "updated_at": now,
            "action": "created",
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


def _search_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Search SQLite memory entries."""
    query = args.get("query", "").strip()
    kind = args.get("kind", "").strip() or None
    scope = args.get("scope", "project").strip() or "project"
    limit = _safe_int(args.get("limit", 50), 1, 1, 500)

    try:
        conn = _connect()
        _init_db(conn)
        sql = "SELECT id, kind, content, summary, scope, tags, created_at, updated_at, checksum FROM runtime_memory WHERE scope=?"
        params: list[Any] = [scope]

        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if query:
            sql += " AND (content LIKE ? OR summary LIKE ?)"
            params.append(f"%{query}%")
            params.append(f"%{query}%")

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return {
            "ok": True,
            "count": len(rows),
            "entries": [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "scope": row["scope"],
                    "tags": row["tags"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "checksum": row["checksum"],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "runtime_sqlite_memory_read",
        "description": "Read runtime SQLite memory entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "default": "note"},
                "scope": {"type": "string", "default": "project"},
                "limit": integer_prop(50, 1, 500),
            },
        },
    },
    {
        "name": "runtime_sqlite_memory_write",
        "description": "Write runtime SQLite memory entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "summary": {"type": "string"},
                "kind": {"type": "string", "default": "note"},
                "scope": {"type": "string", "default": "project"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
        },
    },
    {
        "name": "runtime_sqlite_memory_search",
        "description": "Search runtime SQLite memory entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string"},
                "scope": {"type": "string", "default": "project"},
                "limit": integer_prop(50, 1, 500),
            },
        },
    },
]


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "db": _db_path(),
        "timestamp": _now_iso(),
    }


def serve_handler(request: dict[str, Any]) -> dict[str, Any]:
    """Handle JSON-RPC request."""
    method = request.get("method", "").strip()
    params = request.get("params", {}) or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "").strip()
        args = params.get("arguments", {}) or {}

        if tool_name == "runtime_sqlite_memory_read":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _read_operation(args)}}
        elif tool_name == "runtime_sqlite_memory_write":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _write_operation(args)}}
        elif tool_name == "runtime_sqlite_memory_search":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _search_operation(args)}}
        else:
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

    if method == "health":
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": health_payload()}

    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def read_message(stdin: BinaryIO) -> dict[str, Any] | None:
    """Read a JSON-RPC message from stdin."""
    while True:
        first = stdin.readline()
        if not first:
            return None
        decoded = first.decode("utf-8-sig", errors="replace").strip()
        if decoded:
            break

    if decoded.startswith("{"):
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

    return json.loads(body.decode("utf-8-sig", errors="replace"))


def write_message(stdout: BinaryIO, payload: dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout (JSONL format)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    stdout.write(raw + b"\n")
    stdout.flush()


def main() -> None:
    """Start MCP server on stdio."""
    print(f"{SERVER_NAME} starting on stdio", file=sys.stderr)

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        request = read_message(stdin)
        if request is None:
            break
        response = serve_handler(request)
        if response is not None:
            write_message(stdout, response)


if __name__ == "__main__":
    main()
