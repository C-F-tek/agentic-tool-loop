#!/usr/bin/env python3
"""Read-only Codex ops MCP tools for local service state."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    selected_repo_root,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-codex-ops-mcp"
SERVER_VERSION = "0.1.0-incubator"

DEFAULT_PORTS = [3550, 3551, 3560, 3571, 3572, 3579, 8080, 8888, 8889, 11434, 11435]
DEFAULT_PROCESS_PATTERNS = [
    "uvicorn",
    "aicarmine_broker",
    "vulkan_bridge",
    "open-webui",
    "ollama",
    "ovms",
    "rerank",
    "python",
]


def _diagnostic_preview(value: Any, limit: int = 500) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        try:
            text = str(value)
        except Exception:
            text = f"<unprintable {type(value).__name__}>"
    return text[:limit]


def _safe_int_param(
    value: Any,
    default: int,
    low: int,
    high: int,
    *,
    name: str,
    diagnostics: list[dict[str, Any]] | None = None,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        if diagnostics is not None and value is not None:
            diagnostics.append(
                {
                    "param": name,
                    "error": "invalid_integer",
                    "error_type": type(exc).__name__,
                    "received_preview": _diagnostic_preview(value, 200),
                    "default_used": default,
                    "min": low,
                    "max": high,
                }
            )
        number = default
    return max(low, min(high, number))


@dataclass(frozen=True)
class LocalMcpServer:
    script: str
    health_tool: str | None = None


LOCAL_MCP_SERVERS: dict[str, LocalMcpServer] = {
    "aicarmine_repo_state": LocalMcpServer("repo_state_mcp_server.py", "aicarmine_repo_state_health"),
    "aicarmine_repo_search_det": LocalMcpServer(
        "repo_search_det_mcp_server.py",
        "aicarmine_repo_search_det_health",
    ),
    "aicarmine_repo_validate": LocalMcpServer(
        "repo_validate_mcp_server.py",
        "aicarmine_repo_validate_health",
    ),
    "aicarmine_repo_code": LocalMcpServer("repo_code_mcp_server.py", "aicarmine_repo_code_health"),
    "aicarmine_rag": LocalMcpServer("rag_mcp_server.py"),
    "aicarmine_sqlite_readonly": LocalMcpServer(
        "sqlite_readonly_mcp_server.py",
        "aicarmine_sqlite_readonly_health",
    ),
    "aicarmine_job_artifact": LocalMcpServer("job_artifact_mcp_server.py", "aicarmine_job_artifact_health"),
    "aicarmine_job_view": LocalMcpServer("job_view_mcp_server.py", "aicarmine_job_view_health"),
    "aicarmine_git_readonly": LocalMcpServer("git_readonly_mcp_server.py", "aicarmine_git_readonly_health"),
    "aicarmine_project_memory": LocalMcpServer("project_memory_mcp_server.py", "aicarmine_project_memory_health"),
    "aicarmine_local_subagent": LocalMcpServer(
        "local_subagent_mcp_server.py",
        "aicarmine_local_subagent_health",
    ),
    "aicarmine_agentic_loop_client": LocalMcpServer(
        "agentic_loop_client_mcp_server.py",
        "aicarmine_agentic_loop_health",
    ),
}


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


def integer_array_prop(default: list[int] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "integer"}}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _frame(payload: dict[str, Any], transport: str) -> bytes:
    raw = _json_text(payload).encode("utf-8")
    if transport == "content-length":
        return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
    return raw + b"\n"


def _parse_jsonl(raw: bytes) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.decode("utf-8-sig", errors="replace").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            messages.append(parsed)
    return messages


def _parse_content_length(raw: bytes) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos] in b" \t\r\n":
            pos += 1
        if pos >= len(raw):
            break
        header_end = raw.find(b"\r\n\r\n", pos)
        if header_end < 0:
            break
        header = raw[pos:header_end].decode("ascii", errors="replace")
        length = 0
        for line in header.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() == "content-length":
                try:
                    length = int(value.strip())
                except ValueError:
                    length = 0
                break
        body_start = header_end + 4
        body_end = body_start + length
        if length <= 0 or body_end > len(raw):
            break
        try:
            parsed = json.loads(raw[body_start:body_end].decode("utf-8-sig", errors="replace"))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            messages.append(parsed)
        pos = body_end
    return messages


def _parse_mcp_messages(raw: bytes, transport: str) -> list[dict[str, Any]]:
    if transport == "content-length":
        messages = _parse_content_length(raw)
        if messages:
            return messages
    return _parse_jsonl(raw)


def _message_by_id(messages: list[dict[str, Any]], msg_id: int) -> dict[str, Any]:
    for message in messages:
        if message.get("id") == msg_id:
            return message
    return {}


def _tools_from_list_response(message: dict[str, Any]) -> list[str]:
    raw_result = message.get("result")
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_tools = result.get("tools")
    tools = raw_tools if isinstance(raw_tools, list) else []
    names = [item.get("name") for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str)]
    return sorted(str(name) for name in names)


SECRET_PATTERNS = [
    re.compile(r"(?i)(--(?:api-key|token|password|secret)\s+)([^\s]+)"),
    re.compile(r"(?i)(\b(?:api_key|api-key|token|password|secret)=)([^\s;]+)"),
]


def redact_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>", redacted)
    return redacted


def redact_process_rows(rows: list[Any]) -> list[Any]:
    redacted_rows: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            redacted_rows.append(row)
            continue
        redacted_rows.append({key: redact_text(value) for key, value in row.items()})
    return redacted_rows


def _tool_text_payload(message: dict[str, Any]) -> dict[str, Any]:
    raw_result = message.get("result")
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_content = result.get("content")
    content = raw_content if isinstance(raw_content, list) else []
    first = content[0] if content and isinstance(content[0], dict) else {}
    text = first.get("text")
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"_raw_text": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _script_path(spec: LocalMcpServer) -> Path:
    return Path(__file__).resolve().parent / spec.script


def _mcp_child_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    root_text = str(root)
    env["AICARMINE_CODEX_MCP_REPO_ROOT"] = root_text
    env["CODEX_WORKSPACE_ROOT"] = root_text
    env["AICARMINE_LAB_REPO"] = root_text
    env.setdefault("AICARMINE_USEFUL_TOOLS_ROOT", str(root / "services" / "useful_tools"))
    env.setdefault("AICARMINE_REPO_MCP_MAX_TEXT_CHARS", "24000")
    return env


def _probe_one_mcp(
    *,
    name: str,
    spec: LocalMcpServer,
    root: Path,
    timeout_seconds: int,
    call_health: bool,
    transport: str,
) -> dict[str, Any]:
    script = _script_path(spec)
    if not script.is_file():
        return {
            "ok": False,
            "server": name,
            "error": "mcp_script_not_found",
            "script": str(script),
            "script_exists": False,
        }

    frames = [
        _frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "aicarmine_mcp_inventory", "version": SERVER_VERSION},
                },
            },
            transport,
        ),
        _frame({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, transport),
        _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, transport),
    ]
    if call_health and spec.health_tool:
        frames.append(
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": spec.health_tool, "arguments": {}},
                },
                transport,
            )
        )

    timed_out = False
    returncode: int | None = None
    stdout = b""
    stderr = b""
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(root),
            env=_mcp_child_env(root),
        )
        stdout, stderr = proc.communicate(input=b"".join(frames), timeout=timeout_seconds)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        if proc is not None:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
            returncode = proc.returncode
    except OSError as exc:
        return {
            "ok": False,
            "server": name,
            "error": "mcp_process_start_failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "script": str(script),
            "script_exists": True,
        }

    messages = _parse_mcp_messages(stdout, transport)
    init_message = _message_by_id(messages, 1)
    list_message = _message_by_id(messages, 2)
    health_message = _message_by_id(messages, 3) if call_health and spec.health_tool else {}
    tools = _tools_from_list_response(list_message)
    health = _tool_text_payload(health_message) if health_message else {}

    init_ok = isinstance(init_message.get("result"), dict) and "error" not in init_message
    list_ok = bool(tools) and "error" not in list_message
    health_ok = True
    if call_health and spec.health_tool:
        health_ok = bool(health and health.get("ok") is True)

    return {
        "ok": bool(not timed_out and returncode == 0 and init_ok and list_ok and health_ok),
        "server": name,
        "script": str(script),
        "script_exists": True,
        "transport": transport,
        "returncode": returncode,
        "timed_out": timed_out,
        "initialize_ok": init_ok,
        "tools_list_ok": list_ok,
        "tool_count": len(tools),
        "tools": tools,
        "health_tool": spec.health_tool,
        "health_ok": health_ok,
        "health": health,
        "stderr_tail": stderr.decode("utf-8", errors="replace")[-2000:],
    }


def _requested_servers(args: dict[str, Any]) -> list[str]:
    raw_servers = args.get("servers")
    if isinstance(raw_servers, list) and raw_servers:
        return [str(item) for item in raw_servers if str(item).strip()]
    return list(LOCAL_MCP_SERVERS)


def mcp_inventory_list_targets(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del args
    targets = []
    for name, spec in sorted(LOCAL_MCP_SERVERS.items()):
        script = _script_path(spec)
        targets.append(
            {
                "name": name,
                "script": str(script),
                "script_exists": script.is_file(),
                "health_tool": spec.health_tool,
            }
        )
    return {
        "ok": True,
        "tool": "aicarmine_mcp_inventory_list_targets",
        "mcp_server": SERVER_NAME,
        "repo_root": str(root),
        "targets": targets,
        "allowlist_only": True,
        "test_or_smoke_script_runner": False,
    }


def mcp_inventory_probe(args: dict[str, Any], root: Path) -> dict[str, Any]:
    timeout_seconds = int(args.get("timeout_seconds") or 20)
    timeout_seconds = max(1, min(timeout_seconds, 120))
    call_health = args.get("call_health") is not False
    transport = str(args.get("transport") or "content-length").strip().lower()
    if transport not in {"content-length", "jsonl"}:
        transport = "content-length"

    results: list[dict[str, Any]] = []
    for name in _requested_servers(args):
        spec = LOCAL_MCP_SERVERS.get(name)
        if spec is None:
            results.append({"ok": False, "server": name, "error": "unknown_local_mcp_server"})
            continue
        results.append(
            _probe_one_mcp(
                name=name,
                spec=spec,
                root=root,
                timeout_seconds=timeout_seconds,
                call_health=call_health,
                transport=transport,
            )
        )

    return {
        "ok": all(item.get("ok") is True for item in results),
        "tool": "aicarmine_mcp_inventory_probe",
        "mcp_server": SERVER_NAME,
        "repo_root": str(root),
        "servers": results,
        "server_count": len(results),
        "no_broker_http": True,
        "no_agentic_loop": True,
        "test_or_smoke_script_runner": False,
        "external_tools_skipped": ["aicarmine_vulkan_helper"],
    }


def _powershell_exe() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def _run_powershell_json(script: str, timeout_seconds: int) -> dict[str, Any]:
    executable = _powershell_exe()
    if executable is None:
        return {"ok": False, "error": "powershell_not_found", "data": []}
    try:
        proc = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "powershell_timeout",
            "error_type": type(exc).__name__,
            "timeout_seconds": timeout_seconds,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            "data": [],
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": "powershell_start_failed",
            "error_type": type(exc).__name__,
            "timeout_seconds": timeout_seconds,
            "message_preview": _diagnostic_preview(exc, 500),
            "data": [],
        }
    except PermissionError as exc:
        return {
            "ok": False,
            "error": "powershell_permission_denied",
            "error_type": type(exc).__name__,
            "timeout_seconds": timeout_seconds,
            "message_preview": _diagnostic_preview(exc, 500),
            "data": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": "powershell_os_error",
            "error_type": type(exc).__name__,
            "timeout_seconds": timeout_seconds,
            "message_preview": _diagnostic_preview(exc, 500),
            "data": [],
        }

    stdout = proc.stdout.strip()
    data: Any = []
    json_error = ""
    json_error_type = ""
    if stdout:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            data = {"raw_stdout": stdout[-4000:]}
            json_error = "powershell_json_decode_error"
            json_error_type = type(exc).__name__
    return {
        "ok": proc.returncode == 0 and not json_error,
        "returncode": proc.returncode,
        "data": data,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "error": json_error,
        "error_type": json_error_type,
    }


def service_state_ports(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del root
    diagnostics: list[dict[str, Any]] = []
    raw_ports = args.get("ports")
    if isinstance(raw_ports, list) and raw_ports:
        ports = []
        for index, item in enumerate(raw_ports):
            parsed = _safe_int_param(item, 0, 0, 65535, name=f"ports[{index}]", diagnostics=diagnostics)
            if parsed:
                ports.append(parsed)
    else:
        ports = DEFAULT_PORTS
    ports = [port for port in ports if 0 < port < 65536]
    include_all = args.get("include_all_listeners") is True
    timeout_seconds = _safe_int_param(args.get("timeout_seconds"), 10, 1, 60, name="timeout_seconds", diagnostics=diagnostics)
    ports_json = json.dumps(ports)
    if include_all:
        script = """
$ErrorActionPreference = "Stop"
$Rows = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::1", "::") } |
    Sort-Object LocalPort |
    Select-Object -First 200 LocalAddress,LocalPort,State,OwningProcess
ConvertTo-Json -InputObject @($Rows) -Depth 5 -Compress
"""
    else:
        script = f"""
$ErrorActionPreference = "Stop"
$Ports = ConvertFrom-Json @'
{ports_json}
'@
$Rows = @()
foreach ($Port in $Ports) {{
    $Rows += Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort ([int]$Port) -State Listen -ErrorAction SilentlyContinue |
        Select-Object LocalAddress,LocalPort,State,OwningProcess
}}
ConvertTo-Json -InputObject @($Rows) -Depth 5 -Compress
"""
    result = _run_powershell_json(script, timeout_seconds)
    data = result.get("data")
    rows = data if isinstance(data, list) else ([] if data in (None, "") else [data])
    rows = redact_process_rows(rows)
    return {
        "ok": bool(result.get("ok")),
        "tool": "aicarmine_service_state_ports",
        "mcp_server": SERVER_NAME,
        "ports_requested": ports,
        "include_all_listeners": include_all,
        "listeners": rows,
        "no_http_probes": True,
        "returncode": result.get("returncode"),
        "stderr_tail": result.get("stderr_tail", ""),
        "error": result.get("error", ""),
        "error_type": result.get("error_type", ""),
        **({"input_diagnostics": diagnostics} if diagnostics else {}),
    }


def service_state_processes(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del root
    diagnostics: list[dict[str, Any]] = []
    raw_patterns = args.get("patterns")
    patterns = (
        [str(item) for item in raw_patterns if str(item).strip()]
        if isinstance(raw_patterns, list) and raw_patterns
        else DEFAULT_PROCESS_PATTERNS
    )
    limit = _safe_int_param(args.get("limit"), 50, 1, 200, name="limit", diagnostics=diagnostics)
    timeout_seconds = _safe_int_param(args.get("timeout_seconds"), 10, 1, 60, name="timeout_seconds", diagnostics=diagnostics)
    patterns_json = json.dumps(patterns)
    script = f"""
$ErrorActionPreference = "Stop"
$Patterns = ConvertFrom-Json @'
{patterns_json}
'@
$Rows = Get-CimInstance Win32_Process |
    Where-Object {{
        $Text = "$($_.Name) $($_.CommandLine)"
        $Matched = $false
        foreach ($Pattern in $Patterns) {{
            if ([string]::IsNullOrWhiteSpace([string]$Pattern)) {{
                continue
            }}
            if ($Text -match [regex]::Escape([string]$Pattern)) {{
                $Matched = $true
                break
            }}
        }}
        $Matched
    }} |
    Select-Object -First {limit} ProcessId,Name,ExecutablePath,CommandLine
ConvertTo-Json -InputObject @($Rows) -Depth 5 -Compress
"""
    result = _run_powershell_json(script, timeout_seconds)
    data = result.get("data")
    rows = data if isinstance(data, list) else ([] if data in (None, "") else [data])
    return {
        "ok": bool(result.get("ok")),
        "tool": "aicarmine_service_state_processes",
        "mcp_server": SERVER_NAME,
        "patterns": patterns,
        "limit": limit,
        "processes": rows,
        "returncode": result.get("returncode"),
        "stderr_tail": result.get("stderr_tail", ""),
        "error": result.get("error", ""),
        "error_type": result.get("error_type", ""),
        **({"input_diagnostics": diagnostics} if diagnostics else {}),
    }


def _path_in_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
    except OSError:
        return False
    return resolved == resolved_root or resolved_root in resolved.parents


def _default_log_paths(root: Path, max_files: int) -> tuple[Path, list[Path]]:
    logs_dir = root / "logs"
    if not logs_dir.is_dir():
        return logs_dir, []
    files = [item for item in logs_dir.glob("*.log") if item.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return logs_dir, files[:max_files]


def _read_tail(path: Path, max_lines: int, max_bytes: int) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, os.SEEK_END)
        raw = handle.read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def service_state_logs(args: dict[str, Any], root: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    raw_paths = args.get("paths")
    max_lines = _safe_int_param(args.get("max_lines"), 80, 1, 500, name="max_lines", diagnostics=diagnostics)
    max_files = _safe_int_param(args.get("max_files"), 5, 1, 20, name="max_files", diagnostics=diagnostics)
    max_bytes = _safe_int_param(args.get("max_bytes"), 256000, 1024, 1000000, name="max_bytes", diagnostics=diagnostics)

    if isinstance(raw_paths, list) and raw_paths:
        requested_paths = [Path(str(item)) for item in raw_paths if str(item).strip()]
        logs_dir = root / "logs"
    else:
        logs_dir, requested_paths = _default_log_paths(root, max_files)

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    rejected: list[str] = []
    for requested in requested_paths:
        path = requested if requested.is_absolute() else root / requested
        if not _path_in_root(path, root):
            rejected.append(str(requested))
            continue
        resolved = path.resolve()
        if not resolved.is_file():
            missing.append(str(requested))
            continue
        entries.append(
            {
                "path": str(resolved),
                "size_bytes": resolved.stat().st_size,
                "tail": _read_tail(resolved, max_lines, max_bytes),
            }
        )

    return {
        "ok": True,
        "tool": "aicarmine_service_state_logs",
        "mcp_server": SERVER_NAME,
        "repo_root": str(root),
        "logs_dir": str(logs_dir),
        "logs_dir_exists": logs_dir.is_dir(),
        "entries": entries,
        "entry_count": len(entries),
        "missing": missing,
        "rejected": rejected,
        "read_scope": "repo_root_only",
        **({"input_diagnostics": diagnostics} if diagnostics else {}),
    }


def service_state_snapshot(args: dict[str, Any], root: Path) -> dict[str, Any]:
    ports = service_state_ports(args, root)
    processes = service_state_processes(args, root)
    logs = service_state_logs(args, root)
    return {
        "ok": bool(ports.get("ok") and processes.get("ok") and logs.get("ok")),
        "tool": "aicarmine_service_state_snapshot",
        "mcp_server": SERVER_NAME,
        "repo_root": str(root),
        "ports": ports,
        "processes": processes,
        "logs": logs,
        "no_http_probes": True,
    }


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["incubation_status"] = "isolated_candidate"
        payload["tool_groups"] = ["aicarmine_mcp_inventory", "aicarmine_service_state"]
        payload["no_http_probes"] = True
        payload["no_test_or_smoke_script_runner"] = True
        return payload

    def mcp_inventory_health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return {
            "ok": True,
            "tool": "aicarmine_mcp_inventory_health",
            "mcp_server": SERVER_NAME,
            "repo_root": str(root),
            "known_local_mcp_servers": sorted(LOCAL_MCP_SERVERS),
            "transport_supported": ["content-length", "jsonl"],
            "no_broker_http": True,
            "no_agentic_loop": True,
            "test_or_smoke_script_runner": False,
        }

    def service_health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        logs_dir = root / "logs"
        return {
            "ok": True,
            "tool": "aicarmine_service_state_health",
            "mcp_server": SERVER_NAME,
            "repo_root": str(root),
            "default_ports": DEFAULT_PORTS,
            "default_process_patterns": DEFAULT_PROCESS_PATTERNS,
            "logs_dir": str(logs_dir),
            "logs_dir_exists": logs_dir.is_dir(),
            "no_http_probes": True,
            "read_scope": "repo_root_only_for_logs",
        }

    tools["aicarmine_codex_ops_health"] = ToolSpec(
        name="aicarmine_codex_ops_health",
        description="Report Codex ops MCP health and no-loop/no-HTTP guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_mcp_inventory_health"] = ToolSpec(
        name="aicarmine_mcp_inventory_health",
        description="Report known local MCP servers available for inventory probing over stdio.",
        input_schema=object_schema(),
        handler=mcp_inventory_health,
    )
    tools["aicarmine_mcp_inventory_list_targets"] = ToolSpec(
        name="aicarmine_mcp_inventory_list_targets",
        description="List the static allowlist of local MCP servers available for inventory probing.",
        input_schema=object_schema(),
        handler=mcp_inventory_list_targets,
    )
    tools["aicarmine_mcp_inventory_probe"] = ToolSpec(
        name="aicarmine_mcp_inventory_probe",
        description="Run read-only stdio initialize/list/optional-health inventory probes against local MCP servers.",
        input_schema=object_schema(
            {
                "servers": string_array_prop(sorted(LOCAL_MCP_SERVERS)),
                "timeout_seconds": integer_prop(20, 1, 120),
                "call_health": boolean_prop(True),
                "transport": {"type": "string", "default": "content-length", "enum": ["content-length", "jsonl"]},
            }
        ),
        handler=mcp_inventory_probe,
    )
    tools["aicarmine_service_state_health"] = ToolSpec(
        name="aicarmine_service_state_health",
        description="Report service-state read-only scope and defaults.",
        input_schema=object_schema(),
        handler=service_health,
    )
    tools["aicarmine_service_state_ports"] = ToolSpec(
        name="aicarmine_service_state_ports",
        description="Read local listening sockets without calling HTTP health endpoints.",
        input_schema=object_schema(
            {
                "ports": integer_array_prop(DEFAULT_PORTS),
                "include_all_listeners": boolean_prop(False),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=service_state_ports,
    )
    tools["aicarmine_service_state_processes"] = ToolSpec(
        name="aicarmine_service_state_processes",
        description="Read matching local process command lines with CIM/PowerShell.",
        input_schema=object_schema(
            {
                "patterns": string_array_prop(DEFAULT_PROCESS_PATTERNS),
                "limit": integer_prop(50, 1, 200),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=service_state_processes,
    )
    tools["aicarmine_service_state_logs"] = ToolSpec(
        name="aicarmine_service_state_logs",
        description="Read tails of repo-local log files only.",
        input_schema=object_schema(
            {
                "paths": string_array_prop(),
                "max_lines": integer_prop(80, 1, 500),
                "max_files": integer_prop(5, 1, 20),
                "max_bytes": integer_prop(256000, 1024, 1000000),
            }
        ),
        handler=service_state_logs,
    )
    tools["aicarmine_service_state_snapshot"] = ToolSpec(
        name="aicarmine_service_state_snapshot",
        description="Return one read-only snapshot of ports, process command lines and repo-local log tails.",
        input_schema=object_schema(
            {
                "ports": integer_array_prop(DEFAULT_PORTS),
                "include_all_listeners": boolean_prop(False),
                "patterns": string_array_prop(DEFAULT_PROCESS_PATTERNS),
                "limit": integer_prop(50, 1, 200),
                "paths": string_array_prop(),
                "max_lines": integer_prop(80, 1, 500),
                "max_files": integer_prop(5, 1, 20),
                "max_bytes": integer_prop(256000, 1024, 1000000),
                "timeout_seconds": integer_prop(10, 1, 60),
            }
        ),
        handler=service_state_snapshot,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        root = selected_repo_root()
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_codex_ops_health",
            real_tool="aicarmine_service_state_logs",
            real_args={"max_files": 1, "max_lines": 5},
        )
        result["selected_repo_root"] = str(root)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
