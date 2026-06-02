#!/usr/bin/env python3
"""
AI-Carmine Codex MCP server.

This file is the *single* Codex MCP adapter for the AI-Carmine stack.
It intentionally keeps startup lazy: no broker call, repo scan, SQLite read,
FastAPI import, or useful-tools import happens before the MCP handshake.

Transport:
- MCP JSON-RPC over stdio using Content-Length framing.

Default broker endpoints:
- AICARMINE_VULKAN_AGENT_URL=http://127.0.0.1:3572/vulkan/agent
- AICARMINE_BROKER_BASE_URL=http://127.0.0.1:3572

Operational rule:
- stdout is reserved for MCP frames only.
- diagnostics go to stderr only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO

SERVER_NAME = "aicarmine-codex-mcp"
SERVER_VERSION = "1.2.0"
DEFAULT_AGENT_URL = "http://127.0.0.1:3572/vulkan/agent"
DEFAULT_BROKER_BASE_URL = "http://127.0.0.1:3572"
MAX_TEXT = int(os.environ.get("AICARMINE_MCP_MAX_TEXT_CHARS", "24000"))
DEBUG = os.environ.get("AICARMINE_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}

try:
    from aicarmine_broker.tool_registry import capability_map as _broker_registry_capability_map
except Exception:  # pragma: no cover - MCP startup must remain lazy/robust
    _broker_registry_capability_map = None


def _log(message: str) -> None:
    if DEBUG:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _env_path(name: str, default: str = "") -> Path | None:
    value = os.environ.get(name, default).strip()
    return Path(value).expanduser() if value else None


def _agent_url() -> str:
    return os.environ.get("AICARMINE_VULKAN_AGENT_URL", DEFAULT_AGENT_URL).strip() or DEFAULT_AGENT_URL


def _broker_base_url() -> str:
    return (os.environ.get("AICARMINE_BROKER_BASE_URL", DEFAULT_BROKER_BASE_URL).strip() or DEFAULT_BROKER_BASE_URL).rstrip("/")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _compact_text(value: Any, limit: int = MAX_TEXT) -> str:
    text = value if isinstance(value, str) else _json_dumps(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 180)].rstrip() + "\n\n...[truncated by aicarmine_codex_mcp_server]"


STDIO_TRANSPORT = os.environ.get("AICARMINE_MCP_STDIO_TRANSPORT", "").strip().lower()


def _read_message(stdin: BinaryIO) -> dict[str, Any] | None:
    """
    Read one MCP JSON-RPC message from stdin.

    Codex MCP stdio uses newline-delimited JSON. Older/self-test/LSP-style
    clients may use Content-Length framing. This adapter accepts both and
    replies using the detected transport.
    """
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
            _log("detected stdio transport=jsonl")
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
        _log("detected stdio transport=content-length")
    return json.loads(body.decode("utf-8-sig", errors="replace"))


def _write_message(stdout: BinaryIO, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if STDIO_TRANSPORT == "content-length":
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
    else:
        stdout.write(raw + b"\n")
    stdout.flush()


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 900) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            ctype = (res.headers.get("Content-Type") or "").lower()
            if "application/json" in ctype or raw.strip().startswith((b"{", b"[")):
                return json.loads(raw.decode("utf-8", errors="replace"))
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {body[:4000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URL error {url}: {exc}") from exc


def _call_broker_tool(public_tool: str, args: dict[str, Any]) -> Any:
    args = dict(args or {})
    request_text = (
        args.get("request")
        or args.get("task")
        or args.get("query")
        or args.get("command")
        or f"MCP call {public_tool}"
    )
    timeout = int(args.get("timeout_seconds") or args.get("timeout") or os.environ.get("AICARMINE_MCP_TOOL_TIMEOUT_SECONDS", "900"))
    payload = {
        "function": public_tool,
        "tool_name": public_tool,
        "operation_id": public_tool,
        "requested_function": public_tool,
        "request": str(request_text),
        "parameters": args,
        "arguments": args,
        "allow_command": bool(args.get("allow_command", True)),
        "user_consent": str(args.get("user_consent") or ""),
        "called_by": SERVER_NAME,
    }
    return _http_json("POST", _agent_url(), payload, timeout=timeout)


def _broker_get(path: str, args: dict[str, Any]) -> Any:
    if path.startswith("/"):
        path = path[1:]
    query = ""
    if args:
        query = "?" + urllib.parse.urlencode({k: v for k, v in args.items() if v is not None})
    timeout = int(os.environ.get("AICARMINE_MCP_TOOL_TIMEOUT_SECONDS", "900"))
    return _http_json("GET", f"{_broker_base_url()}/{path}{query}", timeout=timeout)


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _compact_text(value)}], "isError": is_error}


def _repo_root() -> Path:
    return _env_path("AICARMINE_LAB_REPO") or Path.cwd()


def _default_operational_db() -> Path:
    return _env_path("AICARMINE_OPERATIONAL_MEMORY_DB") or (_repo_root() / "output" / "ai_runtime_memory" / "operational_context.sqlite")


def _default_persistent_db() -> Path:
    return _env_path("AICARMINE_PERSISTENT_MEMORY_DB") or (_repo_root() / "indexAI" / "agent_memory" / "agent_memory.sqlite")


def _extend_useful_tools_path() -> None:
    root = _env_path("AICARMINE_USEFUL_TOOLS_ROOT")
    if root and str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _read_memory_table(db_path: Path, table: str, limit: int = 50, query: str = "") -> list[dict[str, Any]]:
    import sqlite3

    if not db_path.exists():
        return []
    limit = max(1, min(int(limit or 50), 200))
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if table not in tables:
            return []
        if query:
            q = f"%{query}%"
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            predicates: list[str] = []
            values: list[Any] = []
            for col in ("summary", "content", "kind", "scope", "source"):
                if col in cols:
                    predicates.append(f"{col} LIKE ?")
                    values.append(q)
            where = " OR ".join(predicates) if predicates else "1=1"
            order = "updated_at DESC" if "updated_at" in cols else "rowid DESC"
            rows = conn.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ?", (*values, limit)).fetchall()
        else:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            order = "updated_at DESC" if "updated_at" in cols else "rowid DESC"
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY {order} LIMIT ?", (limit,)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("tags_json", "metadata_json"):
                if key in item:
                    try:
                        item[key[:-5] if key.endswith("_json") else key] = json.loads(item.get(key) or "{}")
                    except Exception:
                        pass
            if "content" in item and len(str(item["content"])) > 2400:
                item["content_preview"] = str(item["content"])[:2400]
                item.pop("content", None)
            out.append(item)
        return out
    finally:
        conn.close()


def _memory_report(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 50)
    query = str(args.get("query") or "").strip()
    operational_db = Path(args.get("operational_db") or _default_operational_db()).expanduser()
    persistent_db = Path(args.get("persistent_db") or _default_persistent_db()).expanduser()
    return {
        "ok": True,
        "repo_root": str(_repo_root()),
        "useful_tools_root": str(_env_path("AICARMINE_USEFUL_TOOLS_ROOT") or ""),
        "operational_db": str(operational_db),
        "persistent_db": str(persistent_db),
        "operational_exists": operational_db.exists(),
        "persistent_exists": persistent_db.exists(),
        "operational_records": _read_memory_table(operational_db, "operational_memory_records", limit=limit, query=query),
        "persistent_records": _read_memory_table(persistent_db, "memory_records", limit=limit, query=query),
        "note": "Read-only report. No memory writes are performed by this MCP adapter.",
    }


def _memory_state_packet(args: dict[str, Any]) -> dict[str, Any]:
    _extend_useful_tools_path()
    objective = str(args.get("objective") or args.get("task") or args.get("request") or "Codex local task").strip()
    max_memory_chars = int(args.get("max_memory_chars") or 24000)
    report = _memory_report({"limit": int(args.get("limit") or 80), "query": args.get("query") or objective})
    records_payload: list[dict[str, Any]] = []
    for source_name in ("operational_records", "persistent_records"):
        for item in report.get(source_name, []):
            content = str(item.get("content") or item.get("content_preview") or item.get("summary") or "")
            if not content.strip():
                continue
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            records_payload.append(
                {
                    "record_id": str(item.get("record_id") or ""),
                    "kind": str(item.get("kind") or "memory"),
                    "scope": str(item.get("scope") or "project"),
                    "source": str(item.get("source") or source_name),
                    "summary": str(item.get("summary") or content[:900]),
                    "content": content,
                    "tags": [str(t) for t in tags],
                    "confidence": float(item.get("confidence") or 1.0) if str(item.get("confidence") or "").replace(".", "", 1).isdigit() else 1.0,
                }
            )
    try:
        from memory.agent_memory.models import MemoryRecord  # type: ignore
        from memory.agent_memory.state_packet import build_agent_state_packet  # type: ignore

        records = []
        for item in records_payload:
            record = MemoryRecord.from_mapping(item)
            if record is not None:
                records.append(record)
        packet = build_agent_state_packet(
            repo_root=_repo_root(),
            objective=objective,
            records=records,
            max_memory_chars=max_memory_chars,
            packet_name="codex_mcp_agent_state_packet",
        )
        packet["source"] = "memory.agent_memory.state_packet"
        packet["memory_report"] = {k: v for k, v in report.items() if k not in ("operational_records", "persistent_records")}
        return packet
    except Exception as exc:
        return {
            "ok": True,
            "kind": "agent_state_packet_fallback",
            "objective": objective,
            "repo_root": str(_repo_root()),
            "selected_memory": records_payload[:20],
            "source": "fallback_no_import",
            "import_error": str(exc),
            "memory_report": report,
        }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "aicarmine_bridge_health", "description": "Check broker reachability without running a repo action.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "aicarmine_repo_capabilities", "description": "Return deterministic AI-Carmine repo/tool capability map from the existing 3572 broker.", "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_status", "description": "Inspect git/repository status and broker-visible workspace state. Read-only.", "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_tree", "description": "List a bounded repository tree from the broker root. Read-only.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "max_depth": {"type": "integer", "default": 2}, "max_files": {"type": "integer", "default": 200}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_list_files", "description": "List files under a repository path with include/exclude controls. Read-only.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "glob": {"type": "string"}, "max_files": {"type": "integer", "default": 500}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_search", "description": "Run broker-managed repository search. Read-only.", "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "path": {"type": "string", "default": "."}, "mode": {"type": "string", "default": "rg"}, "max_results": {"type": "integer", "default": 80}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_read", "description": "Read one or more repository files through the broker. Read-only.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "paths": {"type": "array", "items": {"type": "string"}}, "max_chars": {"type": "integer", "default": 20000}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_apply_patch", "description": "Apply an exact old_text/new_text patch through the broker. Requires approval before use.", "inputSchema": {"type": "object", "required": ["path", "old_text", "new_text"], "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}, "max_replacements": {"type": "integer", "default": 1}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_write_file", "description": "Write a complete file through the broker. Requires approval before use.", "inputSchema": {"type": "object", "required": ["path", "content"], "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "mode": {"type": "string", "default": "overwrite"}, "encoding": {"type": "string", "default": "utf-8"}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_validate", "description": "Run broker-defined validation commands. May execute local commands; approval policy applies.", "inputSchema": {"type": "object", "properties": {"continue_on_failure": {"type": "boolean", "default": False}, "timeout_seconds": {"type": "integer", "default": 300}}, "additionalProperties": True}},
    {"name": "aicarmine_repo_command", "description": "Run a broker-mediated local command. Dangerous commands require explicit user_consent.", "inputSchema": {"type": "object", "required": ["command"], "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 120}, "user_consent": {"type": "string"}, "allow_command": {"type": "boolean", "default": True}}, "additionalProperties": True}},
    {"name": "aicarmine_vulkan_helper", "description": "Composite repository helper: asks the existing Vulkan broker to choose/evaluate internal tools and return verified context.", "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "request": {"type": "string"}, "query": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 900}}, "additionalProperties": True}},
    {"name": "aicarmine_jobs_status", "description": "Read broker agent-job dashboard JSON from /jobs.json. Read-only.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 50}}, "additionalProperties": False}},
    {"name": "aicarmine_job_detail", "description": "Read a broker agent-job detail JSON from /jobs/{job_id}/json. Read-only.", "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}, "additionalProperties": False}},
    {"name": "aicarmine_memory_report", "description": "Read operational/persistent memory SQLite records. Read-only and lazy.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 50}, "operational_db": {"type": "string"}, "persistent_db": {"type": "string"}}, "additionalProperties": False}},
    {"name": "aicarmine_memory_state_packet", "description": "Build a compact agent_state_packet from local memory records, using existing useful_tools when available.", "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "default": 80}, "max_memory_chars": {"type": "integer", "default": 24000}}, "additionalProperties": False}},
]

INTERNAL_TOOL_MAP = {
    "aicarmine_repo_capabilities": "repo_capabilities",
    "aicarmine_repo_status": "repo_status",
    "aicarmine_repo_tree": "repo_tree",
    "aicarmine_repo_list_files": "repo_list_files",
    "aicarmine_repo_search": "repo_search",
    "aicarmine_repo_read": "repo_read",
    "aicarmine_repo_apply_patch": "repo_apply_patch",
    "aicarmine_repo_write_file": "repo_write_file",
    "aicarmine_repo_validate": "repo_validate",
    "aicarmine_repo_command": "repo_command",
    "aicarmine_vulkan_helper": "vulkan_helper",
}

INSTRUCTIONS = (
    "AI-Carmine MCP exposes local broker tools for Codex. Prefer repo_status/search/read before edits. "
    "Use aicarmine_memory_state_packet when durable operational context matters. "
    "Write/patch/command tools must respect Codex approvals and explicit user consent. "
    "Do not invent files: verify paths with repo_search/repo_read first."
)


def _health() -> dict[str, Any]:
    health_url = f"{_broker_base_url()}/health"
    registry = _broker_registry_capability_map() if _broker_registry_capability_map else {}
    try:
        value = _http_json("GET", health_url, timeout=5)
        return {"ok": True, "url": health_url, "result": value, "registry": registry}
    except Exception as exc:
        return {"ok": False, "url": health_url, "error": type(exc).__name__, "detail": str(exc), "registry": registry}


def _handle_tools_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "aicarmine_bridge_health":
        return _tool_content(_health())
    if name in INTERNAL_TOOL_MAP:
        return _tool_content(_call_broker_tool(INTERNAL_TOOL_MAP[name], arguments))
    if name == "aicarmine_jobs_status":
        return _tool_content(_broker_get("jobs.json", {"limit": arguments.get("limit", 50)}))
    if name == "aicarmine_job_detail":
        job_id = str(arguments.get("job_id") or "").strip()
        if not job_id:
            return _tool_content({"ok": False, "error": "missing job_id"}, is_error=True)
        return _tool_content(_broker_get(f"jobs/{job_id}/json", {}))
    if name == "aicarmine_memory_report":
        return _tool_content(_memory_report(arguments))
    if name == "aicarmine_memory_state_packet":
        return _tool_content(_memory_state_packet(arguments))
    return _tool_content({"ok": False, "error": f"unknown tool: {name}"}, is_error=True)


def _handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if msg_id is None and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            _log("initialize")
            return _ok(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}, "resources": {}, "prompts": {}},
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
            return _ok(msg_id, _handle_tools_call(name, arguments))
        if method == "resources/list":
            return _ok(msg_id, {"resources": []})
        if method == "prompts/list":
            return _ok(msg_id, {"prompts": []})
        if method == "logging/setLevel":
            return _ok(msg_id, {})
        if method.startswith("notifications/"):
            return None
        return _err(msg_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        data = {"exception": str(exc), "traceback": traceback.format_exc()[-6000:]}
        return _err(msg_id, -32000, "AI-Carmine MCP tool error", data)


def serve() -> int:
    _log(f"starting pid={os.getpid()} cwd={Path.cwd()}")
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        message = _read_message(stdin)
        if message is None:
            break
        response = _handle_rpc(message)
        if response is not None:
            _write_message(stdout, response)
    _log("stopped")
    return 0


def _frame(payload: dict[str, Any], transport: str = "jsonl") -> bytes:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if transport == "content-length":
        return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
    return raw + b"\n"


def self_test() -> int:
    transport = "content-length" if "--self-test-content-length" in sys.argv else "jsonl"
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env.pop("AICARMINE_MCP_STDIO_TRANSPORT", None)
    proc = subprocess.Popen(
        [sys.executable, "-u", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "self-test", "version": "1"}}}, transport))
    proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, transport))
    proc.stdin.close()
    out = proc.stdout.read().decode("utf-8", errors="replace")
    err = proc.stderr.read().decode("utf-8", errors="replace")
    rc = proc.wait(timeout=10)
    print(out)
    if err:
        print(err, file=sys.stderr)
    if rc != 0 or "aicarmine_repo_status" not in out:
        return 1
    if transport == "jsonl" and "Content-Length:" in out:
        return 2
    if transport == "content-length" and "Content-Length:" not in out:
        return 3
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
