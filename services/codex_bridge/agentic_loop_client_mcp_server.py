#!/usr/bin/env python3
"""Explicit Codex MCP client for a dedicated canonical agentic-loop broker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, cast
import urllib.error
import urllib.parse
import urllib.request

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-agentic-loop-client-mcp"
SERVER_VERSION = "0.1.0"

RESERVED_PORTS = {3571, 3572, 8080, 11434, 11435}
DEFAULT_RERANKER_PORT = 3550
DEFAULT_RERANKER_URL = (
    os.environ.get("AICARMINE_CONTROLLER_RAG_RERANK_URL")
    or os.environ.get("AICARMINE_RAG_RERANK_URL")
    or os.environ.get("RAG_EXTERNAL_RERANKER_URL")
    or f"http://127.0.0.1:{DEFAULT_RERANKER_PORT}/v3/rerank"
).strip()
DEFAULT_RERANKER_READY_URL = (
    os.environ.get("AICARMINE_RAG_RERANK_READY_URL")
    or os.environ.get("OPENVINO_PROVIDER_HEALTH_URL")
    or f"http://127.0.0.1:{DEFAULT_RERANKER_PORT}/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
).strip()
try:
    DEFAULT_AGENTIC_LOOP_PORT = int(os.environ.get("AICARMINE_AGENTIC_LOOP_CLIENT_PORT", "3579").strip() or "3579")
except ValueError:
    DEFAULT_AGENTIC_LOOP_PORT = 3579
DEFAULT_AGENT_ENDPOINT = os.environ.get("AICARMINE_AGENTIC_LOOP_CLIENT_URL", "").strip()
if not DEFAULT_AGENT_ENDPOINT:
    DEFAULT_AGENT_ENDPOINT = f"http://127.0.0.1:{DEFAULT_AGENTIC_LOOP_PORT}/vulkan/agent"
DEFAULT_HEALTH_ENDPOINT = os.environ.get("AICARMINE_AGENTIC_LOOP_CLIENT_HEALTH_URL", "").strip()
if not DEFAULT_HEALTH_ENDPOINT:
    DEFAULT_HEALTH_ENDPOINT = f"http://127.0.0.1:{DEFAULT_AGENTIC_LOOP_PORT}/health"
CONFIRM_RUN = "aicarmine_agentic_loop_run"
CONFIRM_STATUS = "aicarmine_agentic_loop_status"
CONFIRM_RESULT = "aicarmine_agentic_loop_result"
CONFIRM_ENSURE = "aicarmine_agentic_loop_ensure_broker"
CONFIRM_RERANKER = "aicarmine_agentic_loop_ensure_reranker"
TERMINAL_STATUSES = {
    "completed",
    "failed",
    "blocked_needs_attention",
    "max_steps_reached",
    "cancelled",
    "cancel_requested",
}


def string_prop(default: str | None = None, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if enum is not None:
        schema["enum"] = enum
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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _compact_text(value: Any, max_chars: int) -> tuple[str, bool]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text, False
    suffix = f"\n...[truncated by {SERVER_NAME}; original_chars={len(text)}]"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix, True


def _default_endpoint_for_path(expected_path: str, *, port: int | None = None) -> str:
    selected_port = _safe_int(port, DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    return f"http://127.0.0.1:{selected_port}{expected_path}"


def _endpoint_port(endpoint: str | None, default: int = DEFAULT_AGENTIC_LOOP_PORT) -> int:
    try:
        parsed = urllib.parse.urlparse(str(endpoint or ""))
        if parsed.port is not None:
            return int(parsed.port)
    except Exception:
        pass
    return default


def _validate_endpoint(value: Any, *, expected_path: str, port: Any = None) -> tuple[str | None, dict[str, Any] | None]:
    raw = str(value or "").strip()
    if not raw:
        if port is not None:
            raw = _default_endpoint_for_path(expected_path, port=_safe_int(port, DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535))
        else:
            raw = DEFAULT_AGENT_ENDPOINT if expected_path == "/vulkan/agent" else DEFAULT_HEALTH_ENDPOINT
    parsed = urllib.parse.urlparse(raw)
    port_value = parsed.port
    problem = {
        "ok": False,
        "error": "agentic_loop_endpoint_not_allowlisted",
        "endpoint": raw,
        "expected": _default_endpoint_for_path(expected_path, port=port_value or DEFAULT_AGENTIC_LOOP_PORT),
        "allowed_host": "127.0.0.1",
        "default_port": DEFAULT_AGENTIC_LOOP_PORT,
        "reserved_ports": sorted(RESERVED_PORTS),
        "allowed_path": expected_path,
        "forbidden": ["3571", "3572_shared_openwebui_broker", "11434", "11435", "OpenWebUI", "vulkan_helper_public_bridge"],
    }
    if parsed.scheme != "http":
        return None, problem | {"reason": "scheme_not_http"}
    if parsed.hostname != "127.0.0.1":
        return None, problem | {"reason": "host_not_127_0_0_1"}
    if port_value is None:
        return None, problem | {"reason": "missing_port"}
    if port_value in RESERVED_PORTS:
        return None, problem | {"reason": "reserved_port"}
    if port_value < 1024 or port_value > 65535:
        return None, problem | {"reason": "port_out_of_range"}
    if parsed.path.rstrip("/") != expected_path:
        return None, problem | {"reason": "path_mismatch"}
    if parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None, problem | {"reason": "endpoint_must_not_include_auth_query_or_fragment"}
    return raw, None


def _validate_local_http_endpoint(
    value: Any,
    *,
    default_url: str,
    expected_path_prefix: str,
    default_port: int,
    tool: str,
) -> tuple[str | None, dict[str, Any] | None]:
    raw = str(value or default_url or "").strip()
    parsed = urllib.parse.urlparse(raw)
    problem = {
        "ok": False,
        "tool": tool,
        "error": "local_http_endpoint_not_allowlisted",
        "endpoint": raw,
        "allowed_host": "127.0.0.1",
        "default_port": default_port,
        "allowed_path_prefix": expected_path_prefix,
    }
    if parsed.scheme != "http":
        return None, problem | {"reason": "scheme_not_http"}
    if parsed.hostname != "127.0.0.1":
        return None, problem | {"reason": "host_not_127_0_0_1"}
    if parsed.port is None:
        return None, problem | {"reason": "missing_port"}
    if parsed.path.rstrip("/") and not parsed.path.startswith(expected_path_prefix):
        return None, problem | {"reason": "path_prefix_mismatch"}
    if parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None, problem | {"reason": "endpoint_must_not_include_auth_query_or_fragment"}
    return raw, None


def _http_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    body = None
    headers = {"User-Agent": SERVER_NAME, "Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"_raw_text": text}
            return {
                "ok": True,
                "http_status": response.status,
                "url": url,
                "payload": parsed,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "error": "http_error",
            "http_status": exc.code,
            "url": url,
            "body": text[:4000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "request_failed",
            "url": url,
            "error_type": type(exc).__name__,
            "message": str(exc)[:2000],
        }


def _post_agent(endpoint: str, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    return _http_json(method="POST", url=endpoint, payload=payload, timeout_seconds=timeout_seconds)


def _get_health(endpoint: str, *, timeout_seconds: int) -> dict[str, Any]:
    return _http_json(method="GET", url=endpoint, timeout_seconds=timeout_seconds)


def _json_preview(value: Any, max_chars: int) -> dict[str, Any]:
    text, truncated = _compact_text(value, max_chars)
    return {"text": text, "truncated": truncated}


def _tail_text(path: Path, *, max_chars: int = 4000) -> str:
    try:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _services_root(root: Path) -> Path:
    return root / "services"


def _runtime_dir(root: Path) -> Path:
    return root / "state" / "codex_bridge" / "agentic_loop_client"


def _select_python(root: Path) -> Path:
    env_python = os.environ.get("AICARMINE_LABTOOLS_PYTHON", "").strip()
    if env_python:
        candidate = Path(env_python).expanduser()
        if candidate.is_file():
            return candidate
    labtools_python = root / "venvs" / "labtools" / "Scripts" / "python.exe"
    if labtools_python.is_file():
        return labtools_python
    return Path(sys.executable)


def _port_listening(host: str = "127.0.0.1", port: int = DEFAULT_AGENTIC_LOOP_PORT, *, timeout_seconds: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _path_is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _start_broker_process(
    root: Path,
    *,
    port: int,
    startup_timeout_seconds: int,
    rerank_url: str = DEFAULT_RERANKER_URL,
    reranker_ready_url: str = DEFAULT_RERANKER_READY_URL,
) -> dict[str, Any]:
    services_root = _services_root(root)
    if not services_root.is_dir():
        return {"ok": False, "error": "services_directory_missing", "path": str(services_root)}
    python_exe = _select_python(root)
    if not python_exe.is_file():
        return {"ok": False, "error": "python_executable_missing", "python_executable": str(python_exe)}
    runtime_dir = _runtime_dir(root)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    instance_dir = runtime_dir / f"port-{port}"
    instance_dir.mkdir(parents=True, exist_ok=True)
    workspace = instance_dir / "workspace"
    agent_job_root = workspace / "agent-jobs"
    agent_job_db = agent_job_root / "agent_jobs.sqlite3"
    log_path = instance_dir / f"agentic-loop-{port}.log"
    env = os.environ.copy()
    root_text = str(root.resolve(strict=False))
    env.update(
        {
            "AICARMINE_LAB_REPO": root_text,
            "AICARMINE_REAL_REPO": root_text,
            "AICARMINE_CODEX_MCP_REPO_ROOT": root_text,
            "OPEN_TERMINAL_CWD": root_text,
            "AICARMINE_OPEN_TERMINAL_WORKDIR": root_text,
            "AICARMINE_VULKAN_WORKSPACE": str(workspace),
            "AICARMINE_AGENT_JOB_ROOT": str(agent_job_root),
            "AICARMINE_AGENT_JOB_DB": str(agent_job_db),
            "AICARMINE_AGENT_PUBLIC_BASE_URL": f"http://127.0.0.1:{port}",
            "AICARMINE_VULKAN_AGENT_URL": f"http://127.0.0.1:{port}/vulkan/agent",
            "AICARMINE_BROKER_SERVICE_NAME": f"aicarmine-codex-agentic-loop-{port}",
            "AICARMINE_BROKER_APP_TITLE": f"AI-Carmine Codex Agentic Loop {port}",
            "RAG_EXTERNAL_RERANKER_URL": rerank_url,
            "AICARMINE_RAG_RERANK_URL": rerank_url,
            "AICARMINE_CONTROLLER_RAG_RERANK_URL": rerank_url,
            "AICARMINE_RAG_RERANK_READY_URL": reranker_ready_url,
        }
    )
    command = [
        str(python_exe),
        "-m",
        "uvicorn",
        "aicarmine_vulkan_tool_broker:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_handle = log_path.open("a", encoding="utf-8", errors="replace")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(services_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
    finally:
        log_handle.close()
    deadline = time.monotonic() + max(1, startup_timeout_seconds)
    last_health: dict[str, Any] = {}
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            return {
                "ok": False,
                "error": "broker_process_exited_during_startup",
                "pid": process.pid,
                "exit_code": exit_code,
                "command": command,
                "cwd": str(services_root),
                "log_path": str(log_path),
                "log_tail": _tail_text(log_path),
            }
        health = _get_health(_default_endpoint_for_path("/health", port=port), timeout_seconds=2)
        last_health = health
        if health.get("ok") is True:
            root_check = _broker_root_matches_codex_root(health.get("payload"), root)
            return {
                "ok": bool(root_check.get("ok")),
                "started": True,
                "pid": process.pid,
                "command": command,
                "cwd": str(services_root),
                "port": port,
                "workspace": str(workspace),
                "agent_job_root": str(agent_job_root),
                "agent_job_db": str(agent_job_db),
                "log_path": str(log_path),
                "root_check": root_check,
                "health": _compact_agent_response(health, response_budget_chars=4000, include_raw=False),
            }
        time.sleep(0.5)
    return {
        "ok": False,
        "error": "broker_startup_timeout",
        "pid": process.pid,
        "command": command,
        "cwd": str(services_root),
        "port": port,
        "workspace": str(workspace),
        "agent_job_root": str(agent_job_root),
        "agent_job_db": str(agent_job_db),
        "log_path": str(log_path),
        "log_tail": _tail_text(log_path),
        "last_health": last_health,
    }


def _path_identity(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(Path(text).resolve(strict=False)).lower().rstrip("\\/")
    except Exception:
        return text.lower().rstrip("\\/")


def _broker_root_from_health(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("lab_repo", "workspace"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _broker_root_matches_codex_root(health_payload_value: Any, root: Path) -> dict[str, Any]:
    broker_root = _broker_root_from_health(health_payload_value)
    codex_root = str(root.resolve(strict=False))
    broker_identity = _path_identity(broker_root)
    codex_identity = _path_identity(codex_root)
    return {
        "ok": bool(broker_identity and broker_identity == codex_identity),
        "broker_lab_repo": broker_root,
        "codex_mcp_repo_root": codex_root,
        "broker_lab_repo_identity": broker_identity,
        "codex_mcp_repo_root_identity": codex_identity,
    }


def _reranker_script(root: Path, args: dict[str, Any]) -> Path:
    raw = str(args.get("script") or os.environ.get("OPENVINO_PROVIDER_SCRIPT") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate.resolve(strict=False)
    return root / "services" / "ovms-reranker-npu.ps1"


def _start_reranker_process(
    root: Path,
    *,
    startup_timeout_seconds: int,
    ready_url: str,
    rerank_url: str,
    port: int,
    script: Path,
) -> dict[str, Any]:
    if not script.is_file():
        return {"ok": False, "error": "reranker_script_missing", "script": str(script)}
    if not _path_is_under(script, _services_root(root)):
        return {
            "ok": False,
            "error": "reranker_script_outside_services_root",
            "script": str(script),
            "services_root": str(_services_root(root).resolve(strict=False)),
        }
    runtime_dir = _runtime_dir(root)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / f"reranker-{port}.log"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    env = os.environ.copy()
    env.update(
        {
            "RAG_EXTERNAL_RERANKER_URL": rerank_url,
            "AICARMINE_RAG_RERANK_URL": rerank_url,
            "AICARMINE_CONTROLLER_RAG_RERANK_URL": rerank_url,
            "AICARMINE_RAG_RERANK_READY_URL": ready_url,
        }
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_handle = log_path.open("a", encoding="utf-8", errors="replace")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(script.parent),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
    finally:
        log_handle.close()

    deadline = time.monotonic() + max(1, startup_timeout_seconds)
    last_health: dict[str, Any] = {}
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            return {
                "ok": False,
                "error": "reranker_process_exited_during_startup",
                "pid": process.pid,
                "exit_code": exit_code,
                "command": command,
                "cwd": str(script.parent),
                "log_path": str(log_path),
                "log_tail": _tail_text(log_path),
            }
        health = _get_health(ready_url, timeout_seconds=3)
        last_health = health
        if health.get("ok") is True:
            return {
                "ok": True,
                "started": True,
                "pid": process.pid,
                "command": command,
                "cwd": str(script.parent),
                "port": port,
                "ready_url": ready_url,
                "rerank_url": rerank_url,
                "script": str(script),
                "log_path": str(log_path),
                "health": health,
            }
        time.sleep(1.0)
    return {
        "ok": False,
        "error": "reranker_startup_timeout",
        "pid": process.pid,
        "command": command,
        "cwd": str(script.parent),
        "port": port,
        "ready_url": ready_url,
        "script": str(script),
        "log_path": str(log_path),
        "log_tail": _tail_text(log_path),
        "last_health": last_health,
    }


def _ensure_reranker(args: dict[str, Any], root: Path) -> dict[str, Any]:
    ready_url, ready_problem = _validate_local_http_endpoint(
        args.get("ready_url"),
        default_url=DEFAULT_RERANKER_READY_URL,
        expected_path_prefix="/v2/models/",
        default_port=DEFAULT_RERANKER_PORT,
        tool="aicarmine_agentic_loop_ensure_reranker",
    )
    rerank_url, rerank_problem = _validate_local_http_endpoint(
        args.get("rerank_url"),
        default_url=DEFAULT_RERANKER_URL,
        expected_path_prefix="/v3/rerank",
        default_port=DEFAULT_RERANKER_PORT,
        tool="aicarmine_agentic_loop_ensure_reranker",
    )
    if ready_problem is not None:
        return ready_problem | {"reranker_started": False}
    if rerank_problem is not None:
        return rerank_problem | {"reranker_started": False}
    assert ready_url is not None and rerank_url is not None
    port = _endpoint_port(ready_url, DEFAULT_RERANKER_PORT)
    rerank_port = _endpoint_port(rerank_url, DEFAULT_RERANKER_PORT)
    if rerank_port != port:
        return {
            "ok": False,
            "tool": "aicarmine_agentic_loop_ensure_reranker",
            "error": "reranker_ready_and_rerank_port_mismatch",
            "ready_url": ready_url,
            "rerank_url": rerank_url,
            "ready_port": port,
            "rerank_port": rerank_port,
            "reranker_started": False,
        }
    timeout_seconds = _safe_int(args.get("health_timeout_seconds") or args.get("timeout_seconds"), 5, 1, 20)
    health = _get_health(ready_url, timeout_seconds=timeout_seconds)
    if health.get("ok") is True:
        return {
            "ok": True,
            "tool": "aicarmine_agentic_loop_ensure_reranker",
            "reranker_running": True,
            "reranker_started": False,
            "port": port,
            "ready_url": ready_url,
            "rerank_url": rerank_url,
            "health": health,
        }
    if _port_listening(port=port):
        return {
            "ok": False,
            "tool": "aicarmine_agentic_loop_ensure_reranker",
            "error": "reranker_port_occupied_but_ready_failed",
            "reranker_running": "unknown",
            "reranker_started": False,
            "port": port,
            "ready_url": ready_url,
            "rerank_url": rerank_url,
            "health": health,
            "fix": f"Diagnostica il processo su 127.0.0.1:{port}; il client non lo termina automaticamente.",
        }
    if str(args.get("confirm_ensure_reranker") or "").strip() != CONFIRM_RERANKER:
        return {
            "ok": False,
            "tool": "aicarmine_agentic_loop_ensure_reranker",
            "error": "explicit_reranker_start_confirmation_required",
            "confirm_ensure_reranker_required": CONFIRM_RERANKER,
            "reranker_running": False,
            "reranker_started": False,
            "ready_url": ready_url,
            "rerank_url": rerank_url,
            "health": health,
        }
    script = _reranker_script(root, args)
    startup = _start_reranker_process(
        root,
        startup_timeout_seconds=_safe_int(args.get("startup_timeout_seconds"), 60, 5, 180),
        ready_url=ready_url,
        rerank_url=rerank_url,
        port=port,
        script=script,
    )
    return {
        "tool": "aicarmine_agentic_loop_ensure_reranker",
        "reranker_running": bool(startup.get("ok")),
        "reranker_started": bool(startup.get("started")),
        "ready_url": ready_url,
        "rerank_url": rerank_url,
        **startup,
    }


def _ensure_broker(args: dict[str, Any], root: Path) -> dict[str, Any]:
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    health_endpoint, health_problem = _validate_endpoint(args.get("health_endpoint"), expected_path="/health", port=port)
    if health_problem is not None:
        return health_problem | {"tool": "aicarmine_agentic_loop_ensure_broker", "broker_started": False}
    assert health_endpoint is not None
    port = _endpoint_port(health_endpoint, port)
    reranker_ensure: dict[str, Any] | None = None
    rerank_url = DEFAULT_RERANKER_URL
    reranker_ready_url = DEFAULT_RERANKER_READY_URL
    if _safe_bool(args.get("ensure_reranker"), False):
        reranker_ensure = _ensure_reranker(args, root)
        rerank_url = str(reranker_ensure.get("rerank_url") or rerank_url)
        reranker_ready_url = str(reranker_ensure.get("ready_url") or reranker_ready_url)
        if reranker_ensure.get("ok") is not True:
            return {
                "ok": False,
                "tool": "aicarmine_agentic_loop_ensure_broker",
                "error": reranker_ensure.get("error") or "reranker_ensure_failed",
                "broker_started": False,
                "broker_running": False,
                "reranker_ensure": reranker_ensure,
            }
    else:
        ready_url, ready_problem = _validate_local_http_endpoint(
            args.get("ready_url"),
            default_url=DEFAULT_RERANKER_READY_URL,
            expected_path_prefix="/v2/models/",
            default_port=DEFAULT_RERANKER_PORT,
            tool="aicarmine_agentic_loop_ensure_broker",
        )
        selected_rerank_url, rerank_problem = _validate_local_http_endpoint(
            args.get("rerank_url"),
            default_url=DEFAULT_RERANKER_URL,
            expected_path_prefix="/v3/rerank",
            default_port=DEFAULT_RERANKER_PORT,
            tool="aicarmine_agentic_loop_ensure_broker",
        )
        if ready_problem is not None:
            return ready_problem | {"broker_started": False}
        if rerank_problem is not None:
            return rerank_problem | {"broker_started": False}
        assert ready_url is not None and selected_rerank_url is not None
        ready_port = _endpoint_port(ready_url, DEFAULT_RERANKER_PORT)
        rerank_port = _endpoint_port(selected_rerank_url, DEFAULT_RERANKER_PORT)
        if ready_port != rerank_port:
            return {
                "ok": False,
                "tool": "aicarmine_agentic_loop_ensure_broker",
                "error": "reranker_ready_and_rerank_port_mismatch",
                "broker_started": False,
                "ready_url": ready_url,
                "rerank_url": selected_rerank_url,
                "ready_port": ready_port,
                "rerank_port": rerank_port,
            }
        reranker_ready_url = ready_url
        rerank_url = selected_rerank_url
    timeout_seconds = _safe_int(args.get("health_timeout_seconds") or args.get("timeout_seconds"), 5, 1, 20)
    health = _get_health(health_endpoint, timeout_seconds=timeout_seconds)
    if health.get("ok") is True:
        root_check = _broker_root_matches_codex_root(health.get("payload"), root)
        return {
            "ok": bool(root_check.get("ok")),
            "tool": "aicarmine_agentic_loop_ensure_broker",
            "broker_running": True,
            "broker_started": False,
            "root_check": root_check,
            "health": _compact_agent_response(health, response_budget_chars=4000, include_raw=False),
            **({"reranker_ensure": reranker_ensure} if reranker_ensure is not None else {}),
            **(
                {}
                if root_check.get("ok")
                else {
                    "error": "broker_repo_root_mismatch",
                    "fix": f"Ferma il processo sulla porta dedicata {port} oppure avvialo con AICARMINE_LAB_REPO uguale alla root Codex.",
                }
            ),
        }
    if _port_listening(port=port):
        return {
            "ok": False,
            "tool": "aicarmine_agentic_loop_ensure_broker",
            "error": "broker_port_occupied_but_health_failed",
            "broker_running": "unknown",
            "broker_started": False,
            "health": health,
            "fix": f"Diagnostica il processo che occupa 127.0.0.1:{port}; il client non lo termina automaticamente.",
        }
    if str(args.get("confirm_ensure_broker") or "").strip() != CONFIRM_ENSURE:
        return {
            "ok": False,
            "tool": "aicarmine_agentic_loop_ensure_broker",
            "error": "explicit_broker_start_confirmation_required",
            "confirm_ensure_broker_required": CONFIRM_ENSURE,
            "broker_running": False,
            "broker_started": False,
            "health": health,
        }
    startup = _start_broker_process(
        root,
        port=port,
        startup_timeout_seconds=_safe_int(args.get("startup_timeout_seconds"), 45, 5, 180),
        rerank_url=rerank_url,
        reranker_ready_url=reranker_ready_url,
    )
    return {
        "tool": "aicarmine_agentic_loop_ensure_broker",
        "broker_running": bool(startup.get("ok")),
        "broker_started": bool(startup.get("started")),
        **({"reranker_ensure": reranker_ensure} if reranker_ensure is not None else {}),
        **startup,
    }


def _collect_path_like(value: Any, *, limit: int, out: list[str] | None = None) -> list[str]:
    rows = out if out is not None else []
    if len(rows) >= limit:
        return rows
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"path", "file", "filename", "relpath", "relative_path"} and isinstance(item, str):
                text = item.strip()
                if text and text not in rows:
                    rows.append(text)
                    if len(rows) >= limit:
                        return rows
            _collect_path_like(item, limit=limit, out=rows)
    elif isinstance(value, list):
        for item in value:
            _collect_path_like(item, limit=limit, out=rows)
            if len(rows) >= limit:
                return rows
    return rows


def _tool_history_digest(tool_context: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(tool_context, dict):
        return []
    history = tool_context.get("history")
    if not isinstance(history, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        row = {
            "step": item.get("step"),
            "tool": item.get("tool") or item.get("name"),
            "ok": item.get("ok"),
            "status": item.get("status"),
            "path": item.get("path") or item.get("file"),
            "summary": str(item.get("summary") or item.get("message") or "")[:240],
        }
        rows.append({key: value for key, value in row.items() if value not in (None, "", [], {})})
        if len(rows) >= limit:
            break
    return rows


def _compact_agent_response(response: dict[str, Any], *, response_budget_chars: int, include_raw: bool) -> dict[str, Any]:
    payload = response.get("payload") if response.get("ok") is True else response
    if not isinstance(payload, dict):
        payload = {"value": payload}
    status = str(payload.get("status") or payload.get("final_status") or "").strip()
    tool_context = payload.get("tool_context_for_30b")
    priority_evidence = payload.get("priority_evidence_for_30b")
    payload_index = payload.get("payload_index_for_30b")
    answer = (
        payload.get("answer_for_30b")
        or payload.get("primary_payload_for_30b")
        or payload.get("evidence_guide_for_30b")
        or (tool_context.get("answer_for_30b") if isinstance(tool_context, dict) else "")
        or payload.get("final_summary")
        or payload.get("summary")
        or ""
    )
    answer_preview = _json_preview(answer, response_budget_chars)
    section_budget = max(1200, response_budget_chars // 3)
    compact = {
        "ok": bool(response.get("ok")),
        "http_status": response.get("http_status"),
        "job_id": payload.get("job_id"),
        "status": status,
        "terminal": status in TERMINAL_STATUSES,
        "wait_completed": payload.get("wait_completed"),
        "mode": payload.get("mode"),
        "verdict": payload.get("verdict"),
        "blocked_by": payload.get("blocked_by"),
        "answer_preview": answer_preview["text"],
        "answer_truncated": answer_preview["truncated"],
        "citation_candidates": _collect_path_like(payload, limit=20),
        "tool_history_digest": _tool_history_digest(tool_context),
        "payload_index_preview": _json_preview(payload_index, section_budget)["text"] if payload_index not in (None, "", [], {}) else "",
        "priority_evidence_preview": _json_preview(priority_evidence, section_budget)["text"] if priority_evidence not in (None, "", [], {}) else "",
        "tool_context_keys": sorted(str(key) for key in tool_context.keys()) if isinstance(tool_context, dict) else [],
        "raw_response_keys": sorted(str(key) for key in payload.keys()),
        "raw_response_included": bool(include_raw),
    }
    if include_raw:
        compact["raw_response"] = payload
    else:
        compact["raw_response_omitted"] = True
    return compact


def _task_with_codex_contract(task: str) -> str:
    contract = (
        "\n\nContratto finale per il chiamante Codex: quando finalizzi, restituisci una risposta "
        "compatta con punti chiave, citazioni a path/file o tool-result realmente letti quando "
        "disponibili, limiti espliciti se il job termina parziale/bloccato, e niente rimandi "
        "generici a file locali non presenti nel payload pubblico. Il chiamante reale e' Codex "
        "app tramite MCP dedicato, non OpenWebUI: non dire al chiamante di usare vulkan_helper, "
        "3571 o OpenWebUI come prossimo passo. Se serve citare il canale operativo, cita i tool "
        "MCP aicarmine_agentic_loop_* e il broker dedicato configurato per questa richiesta."
    )
    if "Contratto finale per il chiamante Codex" in task:
        return task
    return task.rstrip() + contract


def _codex_invocation_context(codex_root: str) -> dict[str, Any]:
    return {
        "schema": "agentic_loop_invocation_context.v1",
        "caller": "codex_app",
        "caller_tool": "aicarmine_agentic_loop_client",
        "source": "codex_app_mcp_agentic_loop_client",
        "entrypoint": "mcp",
        "audience": "operator",
        "response_surface": "codex_app_mcp",
        "repo_root": codex_root,
        "expected_broker_lab_repo": codex_root,
        "default_broker_port": DEFAULT_AGENTIC_LOOP_PORT,
        "public_openwebui_bridge": False,
        "openwebui_public_tool_available_to_caller": False,
        "router_tool_name": "vulkan_helper",
        "router_tool_name_is_compatibility_only": True,
        "router_contract": (
            "tool_name=vulkan_helper is only canonical /vulkan/agent router compatibility "
            "for this request; it is not the caller-facing tool surface."
        ),
        "response_contract": (
            "Answer the Codex/operator caller directly. Do not recommend vulkan_helper, "
            "3571 or OpenWebUI as the caller's next step for this MCP invocation."
        ),
        "allowed_followup_surface": [
            "aicarmine_agentic_loop_run",
            "aicarmine_agentic_loop_status",
            "aicarmine_agentic_loop_result",
            "aicarmine_job_artifact",
            "aicarmine_job_view",
        ],
        "forbidden_caller_recommendations": [
            "vulkan_helper",
            "3571",
            "OpenWebUI",
        ],
    }


def _build_start_payload(args: dict[str, Any], root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    task = str(args.get("task") or args.get("request") or args.get("prompt") or "").strip()
    raw_arguments = args.get("arguments")
    arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
    if not task:
        task = str(arguments.get("task") or arguments.get("request") or arguments.get("prompt") or "").strip()
    if not task:
        return None, {"ok": False, "error": "missing_task"}
    if str(args.get("confirm_agentic_loop") or "").strip() != CONFIRM_RUN:
        return None, {
            "ok": False,
            "error": "explicit_agentic_loop_confirmation_required",
            "confirm_agentic_loop_required": CONFIRM_RUN,
            "agentic_loop_called": False,
        }
    wait_seconds = _safe_int(args.get("wait_seconds") or arguments.get("wait_seconds"), 30, 1, 600)
    max_steps = _safe_int(args.get("max_steps") or arguments.get("max_steps"), 20, 1, 80)
    return_mode = str(args.get("return_mode") or arguments.get("return_mode") or "wait").strip().lower()
    if return_mode not in {"wait", "background", "async", "fire_and_forget"}:
        return None, {"ok": False, "error": "invalid_return_mode", "allowed": ["wait", "background", "async", "fire_and_forget"]}
    task_for_loop = _task_with_codex_contract(task) if _safe_bool(args.get("append_codex_final_contract"), True) else task
    codex_root = str(root.resolve(strict=False))
    invocation_context = _codex_invocation_context(codex_root)
    raw_context = arguments.get("context")
    context: dict[str, Any] = dict(cast(dict[str, Any], raw_context)) if isinstance(raw_context, dict) else {}
    context.update(
        {
            "source": "codex_app_mcp_agentic_loop_client",
            "codex_mcp_repo_root": codex_root,
            "expected_broker_lab_repo": codex_root,
            "path_contract": "Dedicated broker AICARMINE_LAB_REPO must equal codex_mcp_repo_root for this client.",
            "invocation_context": invocation_context,
            "caller_context": invocation_context,
        }
    )
    arguments.update(
        {
            "task": task_for_loop,
            "request": task_for_loop,
            "job_action": "start",
            "return_mode": return_mode,
            "wait_seconds": wait_seconds,
            "max_steps": max_steps,
            "lab_repo": codex_root,
            "codex_mcp_repo_root": codex_root,
            "context": context,
            "invocation_context": invocation_context,
            "caller_context": invocation_context,
        }
    )
    for key in ("approval_mode", "user_consent", "job_id", "timeout_seconds"):
        if args.get(key) not in (None, "", [], {}):
            arguments[key] = args.get(key)
    payload = {
        "tool_name": "vulkan_helper",
        "task": task_for_loop,
        "request": task_for_loop,
        "job_action": "start",
        "return_mode": return_mode,
        "wait_seconds": wait_seconds,
        "max_steps": max_steps,
        "lab_repo": codex_root,
        "codex_mcp_repo_root": codex_root,
        "context": context,
        "invocation_context": invocation_context,
        "caller_context": invocation_context,
        "arguments": arguments,
        "codex_agentic_loop_client": True,
    }
    return payload, None


def _build_job_action_payload(args: dict[str, Any], *, action: str, confirm_value: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return None, {"ok": False, "error": "missing_job_id"}
    if str(args.get("confirm_agentic_loop") or "").strip() != confirm_value:
        return None, {
            "ok": False,
            "error": "explicit_agentic_loop_confirmation_required",
            "confirm_agentic_loop_required": confirm_value,
            "agentic_loop_called": False,
        }
    arguments = {
        "job_id": job_id,
        "job_action": action,
    }
    if action == "result":
        arguments["audience"] = str(args.get("audience") or "operator").strip().lower()
    return {
        "tool_name": "vulkan_helper",
        "job_id": job_id,
        "job_action": action,
        "arguments": arguments,
        "codex_agentic_loop_client": True,
    }, None


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "read_only": False,
            "mode": "explicit_codex_to_dedicated_agentic_loop_client",
            "default_port": DEFAULT_AGENTIC_LOOP_PORT,
            "canonical_loop_endpoint": DEFAULT_AGENT_ENDPOINT,
            "health_endpoint": DEFAULT_HEALTH_ENDPOINT,
            "requires_explicit_confirmation": True,
            "confirmation_tokens": {
                "run": CONFIRM_RUN,
                "status": CONFIRM_STATUS,
                "result": CONFIRM_RESULT,
                "ensure_broker": CONFIRM_ENSURE,
                "ensure_reranker": CONFIRM_RERANKER,
            },
            "reranker": {
                "default_port": DEFAULT_RERANKER_PORT,
                "ready_url": DEFAULT_RERANKER_READY_URL,
                "rerank_url": DEFAULT_RERANKER_URL,
                "ensure_tool": "aicarmine_agentic_loop_ensure_reranker",
            },
            "no_broker_http": False,
            "no_agentic_loop": False,
            "mcp_direct_does_not_call": ["3571", "OpenWebUI", "11434", "11435"],
            "note": "The MCP only starts or calls the dedicated broker endpoint and optional local BGE reranker; the broker itself owns planner/model traffic.",
            "codex_mcp_repo_root": str(root),
            "broker_runtime_repo_root": "unknown_without_probe",
        }
    )
    if _safe_bool(args.get("probe_broker"), False):
        endpoint, problem = _validate_endpoint(args.get("health_endpoint"), expected_path="/health", port=args.get("port"))
        if problem is not None:
            payload["broker_probe"] = problem
        else:
            assert endpoint is not None
            timeout_seconds = _safe_int(args.get("timeout_seconds"), 5, 1, 15)
            probe = _get_health(endpoint, timeout_seconds=timeout_seconds)
            payload["broker_probe"] = _compact_agent_response(probe, response_budget_chars=8000, include_raw=_safe_bool(args.get("include_raw"), False))
            raw_probe = probe.get("payload") if probe.get("ok") else {}
            if isinstance(raw_probe, dict):
                payload["broker_runtime_repo_root"] = raw_probe.get("lab_repo") or raw_probe.get("workspace") or "unknown"
                payload["broker_planner_model"] = raw_probe.get("planner_model")
                payload["broker_planner_url"] = raw_probe.get("planner_url")
    return payload


def _capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": "aicarmine_agentic_loop_capabilities",
        "mode": "explicit_codex_to_dedicated_agentic_loop_client",
        "default_port": DEFAULT_AGENTIC_LOOP_PORT,
        "canonical_endpoint": DEFAULT_AGENT_ENDPOINT,
        "codex_mcp_repo_root": str(root),
        "uses_canonical_broker_planner_validator": True,
        "creates_no_local_planner_loop": True,
        "requires_confirmation_for_http": True,
        "can_start_dedicated_broker_for_codex_root": True,
        "can_start_local_bge_reranker": True,
        "start_behavior": "Starts a dedicated broker instance only when its configured port is free and confirm_ensure_broker is supplied.",
        "reranker_start_behavior": "Starts the repo-local OVMS/BGE reranker script only when its configured port is free and confirm_ensure_reranker is supplied.",
        "reranker_ready_url": DEFAULT_RERANKER_READY_URL,
        "reranker_url": DEFAULT_RERANKER_URL,
        "tools": [
            "aicarmine_agentic_loop_health",
            "aicarmine_agentic_loop_capabilities",
            "aicarmine_agentic_loop_ensure_reranker",
            "aicarmine_agentic_loop_ensure_broker",
            "aicarmine_agentic_loop_run",
            "aicarmine_agentic_loop_status",
            "aicarmine_agentic_loop_result",
        ],
        "mcp_direct_does_not_call": ["3571", "OpenWebUI", "11434", "11435"],
        "note": "Broker planner/model traffic is owned by the canonical broker process, not by this MCP.",
    }


def _run(args: dict[str, Any], root: Path) -> dict[str, Any]:
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    endpoint, problem = _validate_endpoint(args.get("endpoint"), expected_path="/vulkan/agent", port=port)
    if problem is not None:
        return problem
    assert endpoint is not None
    port = _endpoint_port(endpoint, port)
    payload, payload_problem = _build_start_payload(args, root)
    if payload_problem is not None:
        return payload_problem
    require_root_match = _safe_bool(args.get("require_broker_repo_root_match"), True)
    broker_root_check: dict[str, Any] = {"ok": None, "skipped": True}
    reranker_ensure: dict[str, Any] | None = None
    ensure_broker = _safe_bool(args.get("ensure_broker"), False)
    if _safe_bool(args.get("ensure_reranker"), False) and not ensure_broker:
        reranker_ensure = _ensure_reranker(args, root)
        if reranker_ensure.get("ok") is not True:
            return {
                "ok": False,
                "tool": "aicarmine_agentic_loop_run",
                "error": reranker_ensure.get("error") or "reranker_ensure_failed",
                "agentic_loop_called": False,
                "broker_health_probe_called": False,
                "reranker_ensure": reranker_ensure,
            }
    if require_root_match:
        if ensure_broker:
            ensure_args = dict(args)
            ensure_args["port"] = port
            ensure = _ensure_broker(ensure_args, root)
            if isinstance(ensure.get("reranker_ensure"), dict):
                reranker_ensure = ensure["reranker_ensure"]
            if ensure.get("ok") is not True:
                return {
                    "ok": False,
                    "tool": "aicarmine_agentic_loop_run",
                    "error": ensure.get("error") or "broker_ensure_failed",
                    "agentic_loop_called": False,
                    "broker_health_probe_called": True,
                    "broker_ensure": ensure,
                }
            ensure_root_check = ensure.get("root_check")
            if isinstance(ensure_root_check, dict):
                broker_root_check = ensure_root_check
        else:
            health_endpoint, health_problem = _validate_endpoint(args.get("health_endpoint"), expected_path="/health", port=port)
            if health_problem is not None:
                return health_problem | {
                    "tool": "aicarmine_agentic_loop_run",
                    "agentic_loop_called": False,
                    "broker_health_probe_called": False,
                    "reason": "cannot_verify_broker_root",
                }
            assert health_endpoint is not None
            health_response = _get_health(health_endpoint, timeout_seconds=_safe_int(args.get("health_timeout_seconds"), 5, 1, 20))
            if health_response.get("ok") is not True:
                return {
                    "ok": False,
                    "tool": "aicarmine_agentic_loop_run",
                    "error": "broker_health_probe_failed",
                    "agentic_loop_called": False,
                    "broker_health_probe_called": True,
                    "broker_health": health_response,
                }
            broker_root_check = _broker_root_matches_codex_root(health_response.get("payload"), root)
        if broker_root_check.get("ok") is not True:
            return {
                "ok": False,
                "tool": "aicarmine_agentic_loop_run",
                "error": "broker_repo_root_mismatch",
                "agentic_loop_called": False,
                "broker_health_probe_called": True,
                "root_check": broker_root_check,
                "fix": f"Avvia il broker dedicato Codex su 127.0.0.1:{port} con AICARMINE_LAB_REPO uguale alla root Codex oppure usa ensure_broker quando la porta e' libera.",
            }
    assert payload is not None
    requested_timeout_seconds = _safe_int(args.get("timeout_seconds"), 120, 15, 900)
    wait_budget_seconds = _safe_int(payload.get("wait_seconds"), 30, 1, 600)
    timeout_seconds = max(requested_timeout_seconds, min(900, wait_budget_seconds + 30))
    response_budget_chars = _safe_int(args.get("response_budget_chars"), 12000, 1000, 60000)
    include_raw = _safe_bool(args.get("include_raw_response"), False)
    response = _post_agent(endpoint, payload, timeout_seconds=timeout_seconds)
    compact = _compact_agent_response(response, response_budget_chars=response_budget_chars, include_raw=include_raw)
    compact.update(
        {
            "tool": "aicarmine_agentic_loop_run",
            "agentic_loop_called": True,
            "broker_health_probe_called": bool(require_root_match),
            "root_check": broker_root_check,
            "endpoint": endpoint,
            "port": port,
            "codex_mcp_repo_root": str(root),
            **({"reranker_ensure": reranker_ensure} if reranker_ensure is not None else {}),
            "request": {
                "return_mode": payload.get("return_mode"),
                "wait_seconds": payload.get("wait_seconds"),
                "max_steps": payload.get("max_steps"),
                "requested_timeout_seconds": requested_timeout_seconds,
                "transport_timeout_seconds": timeout_seconds,
                "task_chars": len(str(payload.get("task") or "")),
            },
        }
    )
    return compact


def _status(args: dict[str, Any], root: Path) -> dict[str, Any]:
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    endpoint, problem = _validate_endpoint(args.get("endpoint"), expected_path="/vulkan/agent", port=port)
    if problem is not None:
        return problem
    assert endpoint is not None
    port = _endpoint_port(endpoint, port)
    payload, payload_problem = _build_job_action_payload(args, action="status", confirm_value=CONFIRM_STATUS)
    if payload_problem is not None:
        return payload_problem
    assert endpoint is not None and payload is not None
    response = _post_agent(endpoint, payload, timeout_seconds=_safe_int(args.get("timeout_seconds"), 30, 5, 120))
    compact = _compact_agent_response(
        response,
        response_budget_chars=_safe_int(args.get("response_budget_chars"), 8000, 1000, 60000),
        include_raw=_safe_bool(args.get("include_raw_response"), False),
    )
    compact.update({"tool": "aicarmine_agentic_loop_status", "agentic_loop_called": True, "endpoint": endpoint, "port": port, "codex_mcp_repo_root": str(root)})
    return compact


def _result(args: dict[str, Any], root: Path) -> dict[str, Any]:
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    endpoint, problem = _validate_endpoint(args.get("endpoint"), expected_path="/vulkan/agent", port=port)
    if problem is not None:
        return problem
    assert endpoint is not None
    port = _endpoint_port(endpoint, port)
    payload, payload_problem = _build_job_action_payload(args, action="result", confirm_value=CONFIRM_RESULT)
    if payload_problem is not None:
        return payload_problem
    assert endpoint is not None and payload is not None
    response = _post_agent(endpoint, payload, timeout_seconds=_safe_int(args.get("timeout_seconds"), 30, 5, 120))
    compact = _compact_agent_response(
        response,
        response_budget_chars=_safe_int(args.get("response_budget_chars"), 16000, 1000, 60000),
        include_raw=_safe_bool(args.get("include_raw_response"), False),
    )
    compact.update({"tool": "aicarmine_agentic_loop_result", "agentic_loop_called": True, "endpoint": endpoint, "port": port, "codex_mcp_repo_root": str(root)})
    return compact


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_agentic_loop_health"] = ToolSpec(
        name="aicarmine_agentic_loop_health",
        description="Report explicit dedicated agentic-loop client health; broker probe is opt-in.",
        input_schema=object_schema(
            {
                "probe_broker": boolean_prop(False),
                "port": integer_prop(DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "health_endpoint": string_prop(DEFAULT_HEALTH_ENDPOINT),
                "timeout_seconds": integer_prop(5, 1, 15),
                "include_raw": boolean_prop(False),
            }
        ),
        handler=health,
    )
    tools["aicarmine_agentic_loop_capabilities"] = ToolSpec(
        name="aicarmine_agentic_loop_capabilities",
        description="Describe the explicit Codex-to-dedicated-broker client and confirmation contract.",
        input_schema=object_schema(),
        handler=_capabilities,
    )
    tools["aicarmine_agentic_loop_ensure_reranker"] = ToolSpec(
        name="aicarmine_agentic_loop_ensure_reranker",
        description="Ensure the local OVMS/BGE reranker is ready on 127.0.0.1:3550; starts the repo-local provider script only with explicit confirmation and only when the configured port is free.",
        input_schema=object_schema(
            {
                "confirm_ensure_reranker": string_prop(),
                "ready_url": string_prop(DEFAULT_RERANKER_READY_URL),
                "rerank_url": string_prop(DEFAULT_RERANKER_URL),
                "script": string_prop(str(Path("services") / "ovms-reranker-npu.ps1")),
                "health_timeout_seconds": integer_prop(5, 1, 20),
                "startup_timeout_seconds": integer_prop(60, 5, 180),
            }
        ),
        handler=_ensure_reranker,
    )
    tools["aicarmine_agentic_loop_ensure_broker"] = ToolSpec(
        name="aicarmine_agentic_loop_ensure_broker",
        description="Ensure a dedicated broker instance is running with AICARMINE_LAB_REPO equal to the Codex MCP repo root; starts it only with explicit confirmation and only when the configured port is free.",
        input_schema=object_schema(
            {
                "confirm_ensure_broker": string_prop(),
                "ensure_reranker": boolean_prop(False),
                "confirm_ensure_reranker": string_prop(),
                "ready_url": string_prop(DEFAULT_RERANKER_READY_URL),
                "rerank_url": string_prop(DEFAULT_RERANKER_URL),
                "port": integer_prop(DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "health_endpoint": string_prop(DEFAULT_HEALTH_ENDPOINT),
                "health_timeout_seconds": integer_prop(5, 1, 20),
                "startup_timeout_seconds": integer_prop(45, 5, 180),
            }
        ),
        handler=_ensure_broker,
    )
    tools["aicarmine_agentic_loop_run"] = ToolSpec(
        name="aicarmine_agentic_loop_run",
        description="Start a canonical broker agentic-loop job on the dedicated Codex port and return a compact Codex-safe terminal summary when available.",
        input_schema=object_schema(
            {
                "task": string_prop(),
                "request": string_prop(),
                "prompt": string_prop(),
                "arguments": object_prop(),
                "confirm_agentic_loop": string_prop(),
                "port": integer_prop(DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "endpoint": string_prop(DEFAULT_AGENT_ENDPOINT),
                "return_mode": string_prop("wait", enum=["wait", "background", "async", "fire_and_forget"]),
                "wait_seconds": integer_prop(30, 1, 600),
                "max_steps": integer_prop(20, 1, 80),
                "timeout_seconds": integer_prop(120, 15, 900),
                "response_budget_chars": integer_prop(12000, 1000, 60000),
                "include_raw_response": boolean_prop(False),
                "append_codex_final_contract": boolean_prop(True),
                "ensure_broker": boolean_prop(False),
                "confirm_ensure_broker": string_prop(),
                "ensure_reranker": boolean_prop(False),
                "confirm_ensure_reranker": string_prop(),
                "ready_url": string_prop(DEFAULT_RERANKER_READY_URL),
                "rerank_url": string_prop(DEFAULT_RERANKER_URL),
                "require_broker_repo_root_match": boolean_prop(True),
                "health_endpoint": string_prop(DEFAULT_HEALTH_ENDPOINT),
                "health_timeout_seconds": integer_prop(5, 1, 20),
                "startup_timeout_seconds": integer_prop(45, 5, 180),
                "approval_mode": string_prop(),
                "user_consent": string_prop(),
                "job_id": string_prop(),
            },
            required=["confirm_agentic_loop"],
        ),
        handler=_run,
    )
    tools["aicarmine_agentic_loop_status"] = ToolSpec(
        name="aicarmine_agentic_loop_status",
        description="Fetch compact status for a dedicated broker agentic-loop job through the canonical router.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "confirm_agentic_loop": string_prop(),
                "port": integer_prop(DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "endpoint": string_prop(DEFAULT_AGENT_ENDPOINT),
                "timeout_seconds": integer_prop(30, 5, 120),
                "response_budget_chars": integer_prop(8000, 1000, 60000),
                "include_raw_response": boolean_prop(False),
            },
            required=["job_id", "confirm_agentic_loop"],
        ),
        handler=_status,
    )
    tools["aicarmine_agentic_loop_result"] = ToolSpec(
        name="aicarmine_agentic_loop_result",
        description="Fetch compact terminal result for a dedicated broker agentic-loop job through the canonical router.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "confirm_agentic_loop": string_prop(),
                "port": integer_prop(DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "audience": string_prop("operator", enum=["openwebui", "operator", "internal"]),
                "endpoint": string_prop(DEFAULT_AGENT_ENDPOINT),
                "timeout_seconds": integer_prop(30, 5, 120),
                "response_budget_chars": integer_prop(16000, 1000, 60000),
                "include_raw_response": boolean_prop(False),
            },
            required=["job_id", "confirm_agentic_loop"],
        ),
        handler=_result,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_agentic_loop_health",
            real_tool="aicarmine_agentic_loop_capabilities",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
