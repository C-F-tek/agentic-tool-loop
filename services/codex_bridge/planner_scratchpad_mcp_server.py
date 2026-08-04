#!/usr/bin/env python3
"""Planner scratchpad MCP server - read/write scratchpad for multi-turn planning."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO

SERVER_NAME = "aicarmine-planner-scratchpad-mcp"
SERVER_VERSION = "0.1.0"
DEFAULT_DB = os.environ.get("AICARMINE_PLANNER_SCRATCHPAD_DB", str(Path.home() / ".aicarmine" / "planner_scratchpad.sqlite"))


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def object_prop() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _db_path() -> str:
    db = os.environ.get("AICARMINE_PLANNER_SCRATCHPAD_DB", DEFAULT_DB)
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
        CREATE TABLE IF NOT EXISTS scratchpad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT 'default',
            key TEXT NOT NULL,
            content TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'project',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scratchpad_key ON scratchpad(key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scratchpad_scope ON scratchpad(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scratchpad_kind ON scratchpad(kind)")
    conn.commit()


def _compute_checksum(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Read scratchpad entry by key."""
    key = args.get("key", "").strip()
    kind = args.get("kind", "default").strip() or "default"
    scope = args.get("scope", "project").strip() or "project"
    offset = _safe_int(args.get("offset", 0), 0, 0, 100000000)
    max_chars = _safe_int(args.get("max_chars", 10000), 100, 100, 1000000)

    if not key:
        return {"ok": False, "error": "key_required", "error_type": "ValidationError"}

    try:
        conn = _connect()
        _init_db(conn)
        row = conn.execute(
            "SELECT content, updated_at, checksum FROM scratchpad WHERE key=? AND kind=? AND scope=?",
            (key, kind, scope),
        ).fetchone()

        if not row:
            return {
                "ok": True,
                "found": False,
                "key": key,
                "kind": kind,
                "scope": scope,
            }

        content = str(row["content"] or "")
        truncated = len(content) > max_chars
        preview = content[offset:offset + max_chars]
        return {
            "ok": True,
            "found": True,
            "key": key,
            "kind": kind,
            "scope": scope,
            "content": preview,
            "truncated": truncated,
            "total_chars": len(content),
            "updated_at": row["updated_at"],
            "checksum": row["checksum"],
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


def _write_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Write scratchpad entry."""
    key = args.get("key", "").strip()
    content = args.get("content", "").strip()
    kind = args.get("kind", "default").strip() or "default"
    scope = args.get("scope", "project").strip() or "project"

    if not key:
        return {"ok": False, "error": "key_required", "error_type": "ValidationError"}

    try:
        conn = _connect()
        _init_db(conn)
        checksum = _compute_checksum(content)
        now = _now_iso()

        existing = conn.execute(
            "SELECT id, checksum FROM scratchpad WHERE key=? AND kind=? AND scope=?",
            (key, kind, scope),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE scratchpad SET content=?, updated_at=?, checksum=? WHERE id=?",
                (content, now, checksum, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO scratchpad (kind, key, content, scope, created_at, updated_at, checksum) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, key, content, scope, now, now, checksum),
            )

        conn.commit()
        return {
            "ok": True,
            "key": key,
            "kind": kind,
            "scope": scope,
            "checksum": checksum,
            "updated_at": now,
            "action": "updated" if existing else "created",
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


def _search_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Search scratchpad entries."""
    pattern = args.get("pattern", "").strip()
    kind = args.get("kind", "").strip() or None
    scope = args.get("scope", "project").strip() or "project"
    limit = _safe_int(args.get("limit", 50), 1, 1, 500)

    try:
        conn = _connect()
        _init_db(conn)
        query = "SELECT key, kind, scope, updated_at, checksum FROM scratchpad WHERE scope=?"
        params: list[Any] = [scope]

        if kind:
            query += " AND kind=?"
            params.append(kind)
        if pattern:
            query += " AND key LIKE ?"
            params.append(f"%{pattern}%")

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return {
            "ok": True,
            "count": len(rows),
            "entries": [
                {
                    "key": row["key"],
                    "kind": row["kind"],
                    "scope": row["scope"],
                    "updated_at": row["updated_at"],
                    "checksum": row["checksum"],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


def _delete_operation(args: dict[str, Any]) -> dict[str, Any]:
    """Delete scratchpad entry."""
    key = args.get("key", "").strip()
    kind = args.get("kind", "default").strip() or "default"
    scope = args.get("scope", "project").strip() or "project"

    if not key:
        return {"ok": False, "error": "key_required", "error_type": "ValidationError"}

    try:
        conn = _connect()
        _init_db(conn)
        conn.execute(
            "DELETE FROM scratchpad WHERE key=? AND kind=? AND scope=?",
            (key, kind, scope),
        )
        conn.commit()
        return {"ok": True, "deleted": True, "key": key}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "error": str(exc)}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "planner_scratchpad_read",
        "description": "Read one planner scratchpad entry by key/kind/scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "kind": {"type": "string", "default": "default"},
                "scope": {"type": "string", "default": "project"},
                "offset": integer_prop(0, 0, 100000000),
                "max_chars": integer_prop(10000, 100, 1000000),
            },
            "required": ["key"],
        },
    },
    {
        "name": "planner_scratchpad_write",
        "description": "Write or update one planner scratchpad entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "content": {"type": "string"},
                "kind": {"type": "string", "default": "default"},
                "scope": {"type": "string", "default": "project"},
            },
            "required": ["key", "content"],
        },
    },
    {
        "name": "planner_scratchpad_search",
        "description": "Search scratchpad entries by pattern/kind/scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "kind": {"type": "string"},
                "scope": {"type": "string", "default": "project"},
                "limit": integer_prop(50, 1, 500),
            },
        },
    },
    {
        "name": "planner_scratchpad_delete",
        "description": "Delete a scratchpad entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "kind": {"type": "string", "default": "default"},
                "scope": {"type": "string", "default": "project"},
            },
            "required": ["key"],
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

        if tool_name == "planner_scratchpad_read":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _read_operation(args)}}
        elif tool_name == "planner_scratchpad_write":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _write_operation(args)}}
        elif tool_name == "planner_scratchpad_search":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _search_operation(args)}}
        elif tool_name == "planner_scratchpad_delete":
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"result": _delete_operation(args)}}
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
