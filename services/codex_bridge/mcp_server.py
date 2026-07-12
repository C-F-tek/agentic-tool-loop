#!/usr/bin/env python3
"""
AI-Carmine Codex App direct MCP server.

Contract
--------
This file is a self-contained MCP stdio adapter for Codex App.

It exposes exactly the historical working aicarmine_tools surface from the
Codex TOML allowlist:

  32 tools:
  - aicarmine_bridge_health
  - terminal_list_files
  - terminal_search_files
  - planner_scratchpad_write
  - runtime_sqlite_memory_write
  - aicarmine_repo_capabilities
  - aicarmine_repo_status
  - aicarmine_repo_tree
  - aicarmine_repo_list_files
  - aicarmine_repo_search
  - aicarmine_repo_rg_search
  - aicarmine_repo_fd_files
  - aicarmine_repo_read
  - aicarmine_repo_ast_grep_search
  - aicarmine_repo_ast_grep_dry_run
  - aicarmine_repo_tree_sitter_parse
  - aicarmine_repo_ctags_symbols
  - aicarmine_repo_jq_query
  - aicarmine_repo_propose_code_edit
  - aicarmine_repo_unidiff_validate
  - aicarmine_repo_git_apply_check
  - aicarmine_repo_apply_patch
  - aicarmine_repo_validate
  - aicarmine_repo_ruff_check
  - aicarmine_repo_pyright_check
  - aicarmine_repo_pytest_run
  - aicarmine_repo_shellcheck
  - aicarmine_repo_semgrep_scan
  - aicarmine_jobs_status
  - aicarmine_job_detail
  - aicarmine_memory_report
  - aicarmine_memory_state_packet

It intentionally does NOT expose:
  - aicarmine_vulkan_helper
  - aicarmine_repo_command
  - aicarmine_repo_write_file
  - terminal_run_command_wait
  - runtime_sqlite_memory_cleanup

No agentic loop:
  - no 3571 bridge call
  - no 3572/vulkan/agent call
  - no _call_broker_tool
  - no HTTP broker dependency for repo tools

Root behavior:
  - Codex-specific root env and cwd win over inherited broker lab-shadow env.
  - AICARMINE_LAB_REPO is accepted only as a legacy fallback.
  - Before broker-tool imports, this MCP process rewrites AICARMINE_LAB_REPO to
    the selected Codex root so import-time aicarmine_broker.config.LAB_REPO is
    coherent for Codex without constraining the OpenWebUI/3572 lab shadow.
  - Server/support paths are derived from __file__.

Transport:
  - JSON-RPC over stdio
  - accepts JSONL and Content-Length frames
  - stdout is reserved for MCP frames only
  - diagnostics go to stderr only
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

SERVER_NAME = "aicarmine-codex-app-mcp"
SERVER_VERSION = "3.0.0-complete-direct"
MAX_TEXT = int(os.environ.get("AICARMINE_MCP_MAX_TEXT_CHARS", "24000"))
RESOURCE_MAX_CHARS = int(os.environ.get("AICARMINE_MCP_RESOURCE_MAX_CHARS", "120000"))
DEBUG = os.environ.get("AICARMINE_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
STDIO_TRANSPORT = os.environ.get("AICARMINE_MCP_STDIO_TRANSPORT", "").strip().lower()
_INITIAL_AICARMINE_LAB_REPO = os.environ.get("AICARMINE_LAB_REPO", "")

_DIRECT_DISPATCHER: Any | None = None
_DISPATCH_REQUEST_CLASS: Any | None = None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _log(message: str) -> None:
    if DEBUG:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _env_path(name: str, default: str = "") -> Path | None:
    value = os.environ.get(name, default).strip()
    return Path(value).expanduser() if value else None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _compact_text(value: Any, limit: int = MAX_TEXT) -> str:
    text = value if isinstance(value, str) else _json_dumps(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 180)].rstrip() + "\n\n...[truncated by aicarmine_codex_app_mcp]"


def _diagnostic_preview(value: Any, limit: int = 500) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        try:
            text = str(value)
        except Exception:
            text = f"<unprintable {type(value).__name__}>"
    return text[:limit]


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _compact_text(value)}], "isError": is_error}


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


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

_CODEX_ROOT_ENV_NAMES = (
    "AICARMINE_CODEX_MCP_REPO_ROOT",
    "CODEX_WORKSPACE_ROOT",
    "CODEX_PROJECT_ROOT",
    "CODEX_CWD",
    "WORKSPACE_ROOT",
    "PROJECT_ROOT",
    "INIT_CWD",
    "PWD",
)


def _services_root() -> Path:
    # .../services/codex_bridge/mcp_server.py -> .../services
    return Path(__file__).resolve().parents[1]


def _server_home_root() -> Path:
    # .../services/codex_bridge/mcp_server.py -> .../AI
    return Path(__file__).resolve().parents[2]


def _server_services_root() -> Path:
    return _services_root()


def _path_git_root(candidate: Path) -> Path | None:
    try:
        current = candidate.resolve()
    except Exception:
        return None

    if current.is_file():
        current = current.parent

    for item in [current, *current.parents]:
        if (item / ".git").exists():
            return item

    try:
        proc = subprocess.run(
            ["git", "-C", str(current), "rev-parse", "--show-toplevel"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    except Exception:
        pass

    return None


def _env_existing_root(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.exists():
        return None
    return _path_git_root(candidate) or candidate.resolve()


def _codex_selected_project_root() -> Path:
    """
    Resolve the active project root.

    Codex/root-specific env and cwd are authoritative for this MCP process.
    AICARMINE_LAB_REPO is accepted only as a legacy fallback so a broker
    lab-shadow inherited from the user environment cannot override the root
    selected by Codex.
    """
    cwd = Path.cwd()
    for name in _CODEX_ROOT_ENV_NAMES:
        root = _env_existing_root(name)
        if root is not None:
            _log(f"selected project root from {name}: {root}")
            return root

    cwd_git_root = _path_git_root(cwd)
    if cwd_git_root is not None:
        _log(f"selected project root from cwd git root: {cwd_git_root}")
        return cwd_git_root

    legacy_lab_root = _env_existing_root("AICARMINE_LAB_REPO")
    if legacy_lab_root is not None:
        _log(f"selected project root from legacy AICARMINE_LAB_REPO: {legacy_lab_root}")
        return legacy_lab_root

    resolved = cwd.resolve()
    _log(f"using cwd as fallback root: {resolved}")
    return resolved


def _codex_root_source(root: Path) -> str:
    for name in _CODEX_ROOT_ENV_NAMES:
        env_root = _env_existing_root(name)
        if env_root is not None and env_root == root:
            return name
    cwd_git_root = _path_git_root(Path.cwd())
    if cwd_git_root is not None and cwd_git_root == root:
        return "cwd_git_root"
    legacy_lab_root = _env_existing_root("AICARMINE_LAB_REPO")
    if legacy_lab_root is not None and legacy_lab_root == root:
        return "AICARMINE_LAB_REPO"
    return "cwd_fallback"


def _repo_root() -> Path:
    # Single operational root for all repo/terminal/memory/job tools.
    return _codex_selected_project_root()


def _canonical_lab_root() -> Path:
    return _repo_root()


def _sync_broker_import_root() -> Path:
    root = _repo_root()
    root_text = str(root)
    os.environ["AICARMINE_CODEX_MCP_REPO_ROOT"] = root_text
    os.environ["AICARMINE_LAB_REPO"] = root_text
    return root


def _useful_tools_root() -> Path:
    env = _env_path("AICARMINE_USEFUL_TOOLS_ROOT")
    if env:
        return env.resolve()
    return (_server_services_root() / "useful_tools").resolve()


def _root_context() -> dict[str, Path]:
    project = _repo_root()
    server_home = _server_home_root()
    server_services = _server_services_root()
    useful = _useful_tools_root()
    return {
        "project_root": project,
        "project_services": project / "services",
        "server_home_root": server_home,
        "server_services_root": server_services,
        "useful_tools_root": useful,
    }


def _allowed_resource_roots() -> list[tuple[str, Path]]:
    ctx = _root_context()
    ordered = [
        ("project_root", ctx["project_root"]),
        ("project_services", ctx["project_services"]),
        ("server_home_root", ctx["server_home_root"]),
        ("server_services_root", ctx["server_services_root"]),
        ("useful_tools_root", ctx["useful_tools_root"]),
    ]

    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for role, root in ordered:
        try:
            resolved = root.resolve()
        except Exception:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((role, resolved))
    return out


def _ensure_import_paths() -> None:
    _sync_broker_import_root()
    for path in (_repo_root(), _server_home_root(), _server_services_root(), _useful_tools_root()):
        value = str(path)
        if path.exists() and value not in sys.path:
            sys.path.insert(0, value)


# ---------------------------------------------------------------------------
# MCP stdio transport
# ---------------------------------------------------------------------------

def _read_message(stdin: BinaryIO) -> dict[str, Any] | None:
    """
    Read one JSON-RPC message.

    Supports JSONL and Content-Length framed messages.
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


# ---------------------------------------------------------------------------
# Direct dispatcher
# ---------------------------------------------------------------------------

def _load_broker_registry_capability_map() -> Any | None:
    _ensure_import_paths()
    try:
        from aicarmine_broker.tool_registry import capability_map  # noqa: PLC0415
    except Exception:
        return None
    return capability_map


def _registry_payload() -> dict[str, Any]:
    registry_loader = _load_broker_registry_capability_map()
    if registry_loader is None:
        return {}
    try:
        value = registry_loader()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _effect_classes_for_internal_tool(internal_tool: str, registry: dict[str, Any] | None = None) -> list[str]:
    registry = registry if isinstance(registry, dict) else _registry_payload()
    surfaces = registry.get("surfaces") if isinstance(registry.get("surfaces"), dict) else {}
    classes: list[str] = []
    for class_name in ("pure_read", "state_mutating", "command_exec", "write_guarded"):
        values = surfaces.get(class_name)
        if isinstance(values, list) and internal_tool in {str(item) for item in values}:
            classes.append(class_name)
    if not classes:
        legacy_read_only = surfaces.get("read_only")
        if isinstance(legacy_read_only, list) and internal_tool in {str(item) for item in legacy_read_only}:
            classes.append("read_only")
    return classes


def _internal_tool_for_requested(name: str) -> str:
    blocked_internal_map = {
        "aicarmine_repo_apply_patch": "repo_apply_patch",
        "aicarmine_repo_command": "repo_command",
        "aicarmine_repo_write_file": "repo_write_file",
        "aicarmine_vulkan_helper": "vulkan_helper",
        "runtime_sqlite_memory_cleanup": "runtime_sqlite_memory_cleanup",
        "terminal_run_command_wait": "terminal_run_command_wait",
        "repo_command": "repo_command",
        "repo_write_file": "repo_write_file",
        "vulkan_helper": "vulkan_helper",
    }
    return INTERNAL_TOOL_MAP.get(name) or blocked_internal_map.get(name, name)


def _blocked_tool_diagnostic(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    internal_tool = _internal_tool_for_requested(name)
    return {
        "requested_tool": name,
        "internal_tool": internal_tool,
        "effect_classes": _effect_classes_for_internal_tool(internal_tool, registry),
        "block_reason": "blocked_by_codex_mcp_direct_policy",
        "allow_command": False,
        "user_consent": "",
    }


def _load_dispatcher() -> Any:
    global _DIRECT_DISPATCHER, _DISPATCH_REQUEST_CLASS

    if _DIRECT_DISPATCHER is not None and _DISPATCH_REQUEST_CLASS is not None:
        return _DIRECT_DISPATCHER

    _ensure_import_paths()
    from aicarmine_broker.application.tool_surface.dispatcher import (  # noqa: PLC0415
        DispatchRequest,
        build_default_dispatcher,
    )

    _DIRECT_DISPATCHER = build_default_dispatcher()
    _DISPATCH_REQUEST_CLASS = DispatchRequest
    return _DIRECT_DISPATCHER


def _direct_dispatch(internal_tool: str, args: dict[str, Any]) -> Any:
    """
    Dispatch directly in-process.

    No HTTP call. No 3571. No 3572/vulkan/agent. No agentic loop.
    """
    effect_classes = _effect_classes_for_internal_tool(internal_tool)
    _log(
        "direct_dispatch_start "
        f"tool={internal_tool} effect_classes={effect_classes} allow_command=False "
        f"args_keys={sorted(dict(args or {}).keys())[:40]}"
    )
    try:
        dispatcher = _load_dispatcher()
        request_class = _DISPATCH_REQUEST_CLASS
        if request_class is None:
            raise RuntimeError("dispatcher request class not loaded")
        request = request_class(
            name=internal_tool,
            args=dict(args or {}),
            root=_repo_root(),
            allow_command=False,
            user_consent="",
        )
        result = dispatcher.dispatch(request)
        _log(f"direct_dispatch_done tool={internal_tool} effect_classes={effect_classes} result_type={type(result).__name__}")
        return result
    except Exception as exc:
        _log(
            "direct_dispatch_failed "
            f"tool={internal_tool} effect_classes={effect_classes} "
            f"error_type={type(exc).__name__} message={_diagnostic_preview(exc, 300)}"
        )
        raise


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _default_operational_db() -> Path:
    return _env_path("AICARMINE_OPERATIONAL_MEMORY_DB") or (
        _repo_root() / "output" / "ai_runtime_memory" / "operational_context.sqlite"
    )


def _default_persistent_db() -> Path:
    return _env_path("AICARMINE_PERSISTENT_MEMORY_DB") or (
        _repo_root() / "indexAI" / "agent_memory" / "agent_memory.sqlite"
    )


def _memory_read_diagnostic(db_path: Path, table: str, stage: str, error: str, exc: Exception | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "db_path": str(db_path),
        "table": table,
        "stage": stage,
        "error": error,
    }
    if exc is not None:
        payload.update(
            {
                "error_type": type(exc).__name__,
                "message_preview": _diagnostic_preview(exc, 500),
            }
        )
    return payload


def _read_memory_table(db_path: Path, table: str, limit: int = 50, query: str = "") -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    import sqlite3

    if not db_path.exists():
        return [], _memory_read_diagnostic(db_path, table, "open", "memory_db_not_found")

    limit = _safe_int(limit, 50, low=1, high=200)
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if table not in tables:
            return [], _memory_read_diagnostic(db_path, table, "schema", "memory_table_not_found")

        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        order = "updated_at DESC" if "updated_at" in cols else "rowid DESC"

        if query:
            q = f"%{query}%"
            predicates: list[str] = []
            values: list[Any] = []
            for col in ("summary", "content", "kind", "scope", "source"):
                if col in cols:
                    predicates.append(f"{col} LIKE ?")
                    values.append(q)
            where = " OR ".join(predicates) if predicates else "1=1"
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ?",
                (*values, limit),
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY {order} LIMIT ?", (limit,)).fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("tags_json", "metadata_json"):
                if key in item:
                    try:
                        item[key[:-5] if key.endswith("_json") else key] = json.loads(item.get(key) or "{}")
                    except json.JSONDecodeError as exc:
                        item[key + "_parse_error"] = True
                        item[key + "_parse_error_type"] = type(exc).__name__
            if "content" in item and len(str(item["content"])) > 2400:
                item["content_preview"] = str(item["content"])[:2400]
                item.pop("content", None)
            out.append(item)
        return out, None
    except sqlite3.OperationalError as exc:
        return [], _memory_read_diagnostic(db_path, table, "sqlite", "sqlite_operational_error", exc)
    except sqlite3.DatabaseError as exc:
        return [], _memory_read_diagnostic(db_path, table, "sqlite", "sqlite_database_error", exc)
    except PermissionError as exc:
        return [], _memory_read_diagnostic(db_path, table, "open", "permission_denied", exc)
    except OSError as exc:
        return [], _memory_read_diagnostic(db_path, table, "filesystem", "os_error", exc)
    finally:
        if conn is not None:
            conn.close()


def _memory_report(args: dict[str, Any]) -> dict[str, Any]:
    limit = _safe_int(args.get("limit"), 50, low=1, high=200)
    query = str(args.get("query") or "").strip()
    operational_db = Path(args.get("operational_db") or _default_operational_db()).expanduser()
    persistent_db = Path(args.get("persistent_db") or _default_persistent_db()).expanduser()
    operational_records, operational_diag = _read_memory_table(
        operational_db,
        "operational_memory_records",
        limit=limit,
        query=query,
    )
    persistent_records, persistent_diag = _read_memory_table(
        persistent_db,
        "memory_records",
        limit=limit,
        query=query,
    )
    diagnostics = [item for item in (operational_diag, persistent_diag) if item is not None]
    payload = {
        "ok": True,
        "tool": "aicarmine_memory_report",
        "mode": "read_only_sqlite",
        "repo_root": str(_repo_root()),
        "operational_db": str(operational_db),
        "persistent_db": str(persistent_db),
        "operational_exists": operational_db.exists(),
        "persistent_exists": persistent_db.exists(),
        "operational_records": operational_records,
        "persistent_records": persistent_records,
    }
    if diagnostics:
        payload["memory_read_diagnostics"] = diagnostics
    return payload


def _memory_state_packet(args: dict[str, Any]) -> dict[str, Any]:
    objective = str(args.get("objective") or args.get("task") or args.get("request") or "Codex local task").strip()
    max_memory_chars = _safe_int(args.get("max_memory_chars"), 24000, low=1000, high=200000)
    report = _memory_report({"limit": _safe_int(args.get("limit"), 80, low=1, high=200), "query": args.get("query") or objective})

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
                    "confidence": _safe_float(item.get("confidence"), 1.0),
                }
            )

    # Prefer the project helper if present, but keep fallback independent.
    try:
        _ensure_import_paths()
        from memory.agent_memory.models import MemoryRecord  # type: ignore  # noqa: PLC0415
        from memory.agent_memory.state_packet import build_agent_state_packet  # type: ignore  # noqa: PLC0415

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
            packet_name="codex_app_mcp_agent_state_packet",
        )
        packet["source"] = "memory.agent_memory.state_packet"
        packet["memory_report"] = {k: v for k, v in report.items() if k not in ("operational_records", "persistent_records")}
        return packet
    except Exception as exc:
        selected: list[dict[str, Any]] = []
        used = 0
        for record in records_payload:
            encoded = _json_dumps(record)
            if used + len(encoded) > max_memory_chars:
                break
            selected.append(record)
            used += len(encoded)

        return {
            "ok": True,
            "kind": "agent_state_packet_fallback",
            "objective": objective,
            "repo_root": str(_repo_root()),
            "selected_memory": selected,
            "source": "fallback_no_import",
            "import_error": str(exc),
            "memory_report": {k: v for k, v in report.items() if k not in ("operational_records", "persistent_records")},
        }


# ---------------------------------------------------------------------------
# Job artifact helpers
# ---------------------------------------------------------------------------

def _job_roots() -> list[Path]:
    candidates = [
        _env_path("AICARMINE_AGENT_JOB_ROOT"),
        _repo_root() / "output" / "agent-jobs",
        _repo_root() / "output" / "agent_jobs",
        _repo_root() / "agent-jobs",
        _repo_root() / "agent_jobs",
        _server_home_root() / "output" / "agent-jobs",
        _server_home_root() / "output" / "agent_jobs",
    ]

    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}


def _jobs_status(args: dict[str, Any]) -> dict[str, Any]:
    limit = _safe_int(args.get("limit"), 50, low=1, high=200)
    jobs: list[dict[str, Any]] = []
    roots = _job_roots()

    for root in roots:
        if not root.exists():
            continue
        for item in root.iterdir():
            if not item.is_dir():
                continue
            marker_files = [
                item / "state.json",
                item / "status.json",
                item / "final.json",
                item / "final.md",
                item / "events.ndjson",
            ]
            existing = [p for p in marker_files if p.exists()]
            if not existing:
                continue
            newest = max(p.stat().st_mtime for p in existing)
            jobs.append(
                {
                    "job_id": item.name,
                    "root": str(item),
                    "modified_unix": newest,
                    "modified_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(newest)),
                    "files": [p.name for p in existing],
                }
            )

    jobs.sort(key=lambda x: float(x.get("modified_unix") or 0), reverse=True)
    return {
        "ok": True,
        "tool": "aicarmine_jobs_status",
        "mode": "local_filesystem_no_http",
        "roots": [str(p) for p in roots],
        "jobs": jobs[:limit],
    }


def _job_detail(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "missing job_id"}

    max_chars = _safe_int(args.get("max_chars"), 24000, low=1000, high=120000)
    for root in _job_roots():
        candidate = root / job_id
        if not candidate.exists() or not candidate.is_dir():
            continue
        payload: dict[str, Any] = {
            "ok": True,
            "tool": "aicarmine_job_detail",
            "mode": "local_filesystem_no_http",
            "job_id": job_id,
            "root": str(candidate),
            "files": {},
        }
        for name in ("state.json", "status.json", "final.json", "final.md", "events.ndjson"):
            path = candidate / name
            if not path.exists():
                continue
            if path.suffix == ".json":
                payload["files"][name] = _safe_read_json(path)
            else:
                payload["files"][name] = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        return payload

    return {"ok": False, "error": "job not found", "job_id": job_id, "roots": [str(p) for p in _job_roots()]}


# ---------------------------------------------------------------------------
# Resources/prompts/roots
# ---------------------------------------------------------------------------

def _mcp_file_uri(path: Path) -> str:
    resolved = path.resolve()
    value = resolved.as_posix()
    if len(value) >= 2 and value[1] == ":":
        return "file:///" + value
    return "file://" + value


def _path_is_under_any_root(child: Path, roots: list[Path]) -> bool:
    try:
        resolved_child = child.resolve()
    except Exception:
        return False

    child_text = str(resolved_child).lower().rstrip("\\/")
    for root in roots:
        try:
            resolved_root = root.resolve()
        except Exception:
            continue

        try:
            resolved_child.relative_to(resolved_root)
            return True
        except ValueError:
            pass

        root_text = str(resolved_root).lower().rstrip("\\/")
        if child_text == root_text or child_text.startswith(root_text + "\\") or child_text.startswith(root_text + "/"):
            return True

    return False


def _resource_path_from_uri(uri: str) -> Path:
    uri = str(uri or "").strip()
    if not uri:
        raise ValueError("missing resource uri")

    parsed = urlparse(uri)

    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"unsupported resource uri scheme: {parsed.scheme}")

    if parsed.scheme == "file":
        raw_path = unquote(parsed.path or "")

        if raw_path.startswith("/") and len(raw_path) >= 4 and raw_path[2] == ":":
            raw_path = raw_path[1:]

        if parsed.netloc:
            raise ValueError(f"unsupported file URI netloc: {parsed.netloc}")

        candidate = Path(raw_path).resolve()
    else:
        candidate = (_repo_root() / uri).resolve()

    roots = [root for _role, root in _allowed_resource_roots()]
    if not _path_is_under_any_root(candidate, roots):
        raise ValueError(
            "resource path outside allowed roots: "
            f"path={candidate}; roots={[str(r) for r in roots]}"
        )

    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))

    return candidate


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix == ".css":
        return "text/css"
    if suffix == ".js":
        return "text/javascript"
    if suffix == ".json":
        return "application/json"
    if suffix in {".md", ".txt", ".py", ".ps1", ".bat", ".cmd", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".env", ".log"}:
        return "text/plain"
    return "text/plain"


def _handle_resources_list(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "resources": [
            {
                "uri": _mcp_file_uri(root),
                "name": role,
                "mimeType": "inode/directory",
                "description": f"{role}: {root}",
            }
            for role, root in _allowed_resource_roots()
        ]
    }


def _handle_resources_read(params: dict[str, Any]) -> dict[str, Any]:
    uri = str(params.get("uri") or "")
    max_chars = _safe_int(os.environ.get("AICARMINE_MCP_RESOURCE_MAX_CHARS"), RESOURCE_MAX_CHARS, low=1000, high=2_000_000)

    resource_path = _resource_path_from_uri(uri)
    data = resource_path.read_text(encoding="utf-8", errors="replace")

    truncated = False
    if len(data) > max_chars:
        data = data[:max_chars]
        truncated = True

    if truncated:
        data += "\n\n...[truncated by aicarmine_tools resources/read]"

    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": _guess_mime_type(resource_path),
                "text": data,
            }
        ]
    }


def _handle_resources_templates_list(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceTemplates": [
            {
                "uriTemplate": _mcp_file_uri(root) + "/{path}",
                "name": f"{role}_file",
                "description": f"Read-only file resource under {role}: {root}",
                "mimeType": "text/plain",
            }
            for role, root in _allowed_resource_roots()
        ]
    }


def _handle_roots_list(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "roots": [
            {
                "uri": _mcp_file_uri(root),
                "name": role,
            }
            for role, root in _allowed_resource_roots()
        ]
    }


def _handle_prompts_list(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompts": [
            {
                "name": "aicarmine_mcp_only",
                "description": "Use only aicarmine_tools MCP methods; no shell fallback.",
                "arguments": [],
            }
        ]
    }


def _handle_prompts_get(params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name") or "")
    if name and name != "aicarmine_mcp_only":
        raise ValueError(f"unknown prompt: {name}")

    return {
        "description": "AI-Carmine MCP-only operating prompt",
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "Use only the MCP server aicarmine_tools. "
                        "Do not use shell, PowerShell, or internal fallback tools. "
                        "If aicarmine_tools is not callable, answer exactly "
                        "MCP_AICARMINE_TOOLS_NOT_AVAILABLE."
                    ),
                },
            }
        ],
    }


def _handle_completion_complete(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "completion": {
            "values": [],
            "total": 0,
            "hasMore": False,
        }
    }


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _schema(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": True,
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema("aicarmine_bridge_health", "Local MCP health. No HTTP call and no agentic loop."),
    _schema("terminal_list_files", "Direct terminal-style file listing through in-process dispatcher. Read-only.", {"path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 200}}),
    _schema("terminal_search_files", "Direct terminal-style file search through in-process dispatcher. Read-only.", {"query": {"type": "string"}, "path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 80}}, ["query"]),
    _schema("planner_scratchpad_write", "Write planner scratchpad memory through direct dispatcher. No agentic loop.", {"content": {"type": "string"}, "key": {"type": "string"}, "scope": {"type": "string", "default": "codex_app"}}),
    _schema("runtime_sqlite_memory_write", "Write runtime SQLite memory through direct dispatcher. No agentic loop.", {"content": {"type": "string"}, "summary": {"type": "string"}, "kind": {"type": "string", "default": "codex_note"}, "scope": {"type": "string", "default": "project"}, "tags": {"type": "array", "items": {"type": "string"}}}),
    _schema("aicarmine_repo_capabilities", "Direct repo capability map through in-process dispatcher. Read-only."),
    _schema("aicarmine_repo_status", "Direct git/repository status through in-process dispatcher. Read-only."),
    _schema("aicarmine_repo_tree", "Direct bounded repository tree listing. Read-only.", {"path": {"type": "string", "default": "."}, "max_depth": {"type": "integer", "default": 2}, "max_files": {"type": "integer", "default": 200}}),
    _schema("aicarmine_repo_list_files", "Direct file listing under a repo path. Read-only.", {"path": {"type": "string", "default": "."}, "glob": {"type": "string"}, "max_files": {"type": "integer", "default": 500}}),
    _schema("aicarmine_repo_search", "Direct broker-managed repository search. Read-only.", {"query": {"type": "string"}, "path": {"type": "string", "default": "."}, "mode": {"type": "string", "default": "rg"}, "max_results": {"type": "integer", "default": 80}}, ["query"]),
    _schema("aicarmine_repo_rg_search", "Direct ripgrep-style repository search wrapper. Read-only.", {"query": {"type": "string"}, "path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 80}}, ["query"]),
    _schema("aicarmine_repo_fd_files", "Direct fd-style file discovery wrapper. Read-only.", {"pattern": {"type": "string", "default": ""}, "path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 200}}),
    _schema("aicarmine_repo_read", "Direct read of one or more repo-relative files. Read-only.", {"path": {"type": "string"}, "paths": {"type": "array", "items": {"type": "string"}}, "max_chars": {"type": "integer", "default": 20000}}),
    _schema("aicarmine_repo_ast_grep_search", "Direct ast-grep search where available. Read-only.", {"query": {"type": "string"}, "path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 80}}, ["query"]),
    _schema("aicarmine_repo_ast_grep_dry_run", "Direct ast-grep dry-run. Read-only.", {"query": {"type": "string"}, "path": {"type": "string", "default": "."}}, ["query"]),
    _schema("aicarmine_repo_tree_sitter_parse", "Direct tree-sitter parse helper where available. Read-only.", {"path": {"type": "string"}}, ["path"]),
    _schema("aicarmine_repo_ctags_symbols", "Direct ctags symbol extraction where available. Read-only.", {"path": {"type": "string", "default": "."}, "max_results": {"type": "integer", "default": 200}}),
    _schema("aicarmine_repo_jq_query", "Direct jq query helper for JSON files. Read-only.", {"path": {"type": "string"}, "query": {"type": "string"}}, ["path", "query"]),
    _schema("aicarmine_repo_propose_code_edit", "Report-only code edit proposal helper. Does not write files.", {"path": {"type": "string"}, "request": {"type": "string"}}, ["path", "request"]),
    _schema("aicarmine_repo_unidiff_validate", "Validate a unified diff without applying it.", {"diff": {"type": "string"}}, ["diff"]),
    _schema("aicarmine_repo_git_apply_check", "Run git-apply style patch check through the repo tool wrapper.", {"diff": {"type": "string"}}, ["diff"]),
    _schema("aicarmine_repo_apply_patch", "Apply exact old_text/new_text patch. Only exposed write tool.", {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}, "max_replacements": {"type": "integer", "default": 1}}, ["path", "old_text", "new_text"]),
    _schema("aicarmine_repo_validate", "Run broker-defined validation. No free-form command input.", {"continue_on_failure": {"type": "boolean", "default": False}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_repo_ruff_check", "Run repo ruff check wrapper.", {"path": {"type": "string", "default": "."}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_repo_pyright_check", "Run repo pyright check wrapper.", {"path": {"type": "string", "default": "."}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_repo_pytest_run", "Run repo pytest wrapper with bounded args from the tool implementation.", {"path": {"type": "string", "default": "."}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_repo_shellcheck", "Run shellcheck wrapper where available.", {"path": {"type": "string", "default": "."}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_repo_semgrep_scan", "Run semgrep scan wrapper where available.", {"path": {"type": "string", "default": "."}, "timeout_seconds": {"type": "integer", "default": 300}}),
    _schema("aicarmine_jobs_status", "Read local agent-job artifacts from filesystem. No HTTP call.", {"limit": {"type": "integer", "default": 50}}),
    _schema("aicarmine_job_detail", "Read a local agent-job artifact directory by id. No HTTP call.", {"job_id": {"type": "string"}, "max_chars": {"type": "integer", "default": 24000}}, ["job_id"]),
    _schema("aicarmine_memory_report", "Read operational/persistent memory SQLite records. Read-only.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 50}, "operational_db": {"type": "string"}, "persistent_db": {"type": "string"}}),
    _schema("aicarmine_memory_state_packet", "Build compact context packet from read-only local memory records.", {"objective": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "default": 80}, "max_memory_chars": {"type": "integer", "default": 24000}}),
]

INTERNAL_TOOL_MAP: dict[str, str] = {
    "terminal_list_files": "terminal_list_files",
    "terminal_search_files": "terminal_search_files",
    "planner_scratchpad_write": "planner_scratchpad_write",
    "runtime_sqlite_memory_write": "runtime_sqlite_memory_write",
    "aicarmine_repo_capabilities": "repo_capabilities",
    "aicarmine_repo_status": "repo_status",
    "aicarmine_repo_tree": "repo_tree",
    "aicarmine_repo_list_files": "repo_list_files",
    "aicarmine_repo_search": "repo_search",
    "aicarmine_repo_rg_search": "repo_rg_search",
    "aicarmine_repo_fd_files": "repo_fd_files",
    "aicarmine_repo_read": "repo_read",
    "aicarmine_repo_ast_grep_search": "repo_ast_grep_search",
    "aicarmine_repo_ast_grep_dry_run": "repo_ast_grep_dry_run",
    "aicarmine_repo_tree_sitter_parse": "repo_tree_sitter_parse",
    "aicarmine_repo_ctags_symbols": "repo_ctags_symbols",
    "aicarmine_repo_jq_query": "repo_jq_query",
    "aicarmine_repo_propose_code_edit": "repo_propose_code_edit",
    "aicarmine_repo_unidiff_validate": "repo_unidiff_validate",
    "aicarmine_repo_git_apply_check": "repo_git_apply_check",
    "aicarmine_repo_apply_patch": "repo_apply_patch",
    "aicarmine_repo_validate": "repo_validate",
    "aicarmine_repo_ruff_check": "repo_ruff_check",
    "aicarmine_repo_pyright_check": "repo_pyright_check",
    "aicarmine_repo_pytest_run": "repo_pytest_run",
    "aicarmine_repo_shellcheck": "repo_shellcheck",
    "aicarmine_repo_semgrep_scan": "repo_semgrep_scan",
}

BLOCKED_TOOLS = {
    "aicarmine_vulkan_helper",
    "aicarmine_repo_command",
    "aicarmine_repo_write_file",
    "terminal_run_command_wait",
    "runtime_sqlite_memory_cleanup",
    "repo_command",
    "repo_write_file",
    "vulkan_helper",
}


# ---------------------------------------------------------------------------
# Health and tool router
# ---------------------------------------------------------------------------

def _health() -> dict[str, Any]:
    registry = _registry_payload()
    root = _repo_root()
    return {
        "ok": True,
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "mode": "codex_app_direct_dispatch_no_agentic_loop",
        "process_cwd": str(Path.cwd()),
        "resolved_project_root": str(root),
        "root_source": _codex_root_source(root),
        "root_context": {k: str(v) for k, v in _root_context().items()},
        "server_script": str(Path(__file__).resolve()),
        "python_executable": sys.executable,
        "transport": STDIO_TRANSPORT or "auto",
        "initial_aicarmine_lab_repo": _INITIAL_AICARMINE_LAB_REPO,
        "effective_broker_import_lab_repo": os.environ.get("AICARMINE_LAB_REPO"),
        "codex_mcp_repo_root": os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT"),
        "registry_loaded": bool(registry),
        "registry": registry,
        "tools_count": len(TOOL_SCHEMAS),
        "tools": [tool["name"] for tool in TOOL_SCHEMAS],
        "blocked_tool_diagnostics": [_blocked_tool_diagnostic(name, registry) for name in sorted(BLOCKED_TOOLS)],
        "env_seen": {
            "AICARMINE_LAB_REPO": os.environ.get("AICARMINE_LAB_REPO"),
            "AICARMINE_USEFUL_TOOLS_ROOT": os.environ.get("AICARMINE_USEFUL_TOOLS_ROOT"),
            "CODEX_WORKSPACE_ROOT": os.environ.get("CODEX_WORKSPACE_ROOT"),
            "CODEX_PROJECT_ROOT": os.environ.get("CODEX_PROJECT_ROOT"),
            "CODEX_CWD": os.environ.get("CODEX_CWD"),
            "WORKSPACE_ROOT": os.environ.get("WORKSPACE_ROOT"),
            "PROJECT_ROOT": os.environ.get("PROJECT_ROOT"),
            "PWD": os.environ.get("PWD"),
        },
        "disabled_by_design": sorted(BLOCKED_TOOLS),
    }


def _handle_tools_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}

    if name in BLOCKED_TOOLS:
        return _tool_content(
            {
                "ok": False,
                "error": f"tool blocked by MCP policy: {name}",
                **_blocked_tool_diagnostic(name),
            },
            is_error=True,
        )

    if name == "aicarmine_bridge_health":
        return _tool_content(_health())

    if name in INTERNAL_TOOL_MAP:
        return _tool_content(_direct_dispatch(INTERNAL_TOOL_MAP[name], arguments))

    if name == "aicarmine_jobs_status":
        return _tool_content(_jobs_status(arguments))

    if name == "aicarmine_job_detail":
        return _tool_content(_job_detail(arguments))

    if name == "aicarmine_memory_report":
        return _tool_content(_memory_report(arguments))

    if name == "aicarmine_memory_state_packet":
        return _tool_content(_memory_state_packet(arguments))

    return _tool_content({"ok": False, "error": f"unknown tool: {name}"}, is_error=True)


INSTRUCTIONS = (
    "AI-Carmine Codex App MCP direct mode. "
    "Use only aicarmine_tools MCP methods for this server. "
    "No 3571, no 3572/vulkan/agent, no vulkan_helper, no HTTP broker tool loop. "
    "Use repo_status/list/search/read before edits. "
    "Use repo_apply_patch as the write path exposed by this 32-tool surface. "
    "Use memory_report and memory_state_packet for durable context. "
    "Do not invent files: verify paths with repo_search/repo_read first."
)


# ---------------------------------------------------------------------------
# JSON-RPC router
# ---------------------------------------------------------------------------

def _handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    raw_params = message.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

    if msg_id is None and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            return _ok(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                        "roots": {"listChanged": False},
                        "completion": {},
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
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            return _ok(msg_id, _handle_tools_call(name, arguments))

        if method == "resources/list":
            return _ok(msg_id, _handle_resources_list(params))

        if method == "resources/read":
            return _ok(msg_id, _handle_resources_read(params))

        if method == "resources/templates/list":
            return _ok(msg_id, _handle_resources_templates_list(params))

        if method == "prompts/list":
            return _ok(msg_id, _handle_prompts_list(params))

        if method == "prompts/get":
            return _ok(msg_id, _handle_prompts_get(params))

        if method == "completion/complete":
            return _ok(msg_id, _handle_completion_complete(params))

        if method == "roots/list":
            return _ok(msg_id, _handle_roots_list(params))

        if method == "logging/setLevel":
            return _ok(msg_id, {})

        if method.startswith("notifications/"):
            return None

        return _err(msg_id, -32601, f"Method not found: {method}")

    except Exception as exc:
        data = {"exception": str(exc), "traceback": traceback.format_exc()[-6000:]}
        return _err(msg_id, -32000, "AI-Carmine Codex App MCP tool error", data)


# ---------------------------------------------------------------------------
# Serve/self-test/main
# ---------------------------------------------------------------------------

def serve() -> int:
    root = _sync_broker_import_root()
    _log(f"starting pid={os.getpid()} cwd={Path.cwd()} repo_root={root}")
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
        cwd=Path.cwd(),
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

    proc.stdin.write(_frame({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "self-test", "version": "1"},
        },
    }, transport))
    proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, transport))
    proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}, transport))
    proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 4, "method": "roots/list", "params": {}}, transport))
    proc.stdin.close()

    out = proc.stdout.read().decode("utf-8", errors="replace")
    err = proc.stderr.read().decode("utf-8", errors="replace")
    rc = proc.wait(timeout=20)

    print(out)
    if err:
        print(err, file=sys.stderr)

    if rc != 0:
        return 1

    required = {
        "aicarmine_bridge_health",
        "terminal_list_files",
        "terminal_search_files",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_write",
        "aicarmine_memory_report",
        "aicarmine_memory_state_packet",
    }
    missing = sorted(name for name in required if name not in out)
    if missing:
        print(f"missing required tools: {missing}", file=sys.stderr)
        return 2

    forbidden = {
        "aicarmine_vulkan_helper",
        "aicarmine_repo_command",
        "aicarmine_repo_write_file",
        "terminal_run_command_wait",
        "runtime_sqlite_memory_cleanup",
    }
    exposed_forbidden = sorted(name for name in forbidden if name in out)
    if exposed_forbidden:
        print(f"forbidden tools exposed: {exposed_forbidden}", file=sys.stderr)
        return 3

    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--self-test-content-length" in sys.argv:
        return self_test()
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
