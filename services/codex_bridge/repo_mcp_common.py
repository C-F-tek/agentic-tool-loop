#!/usr/bin/env python3
"""Shared stdio MCP helpers for deterministic AI-Carmine repo tools."""

from __future__ import annotations

import bz2
import json
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable

SERVICES_ROOT = Path(__file__).resolve().parents[1]
REPO_HOME_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

MAX_TEXT = int(os.environ.get("AICARMINE_REPO_MCP_MAX_TEXT_CHARS", "24000"))
STDIO_TRANSPORT = os.environ.get("AICARMINE_REPO_MCP_STDIO_TRANSPORT", "").strip().lower()
DEBUG = os.environ.get("AICARMINE_REPO_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
INITIAL_AICARMINE_LAB_REPO = os.environ.get("AICARMINE_LAB_REPO", "")
COMPRESSION_ENABLED = os.environ.get("AICARMINE_REPO_MCP_COMPRESSION", "0").strip().lower() in {"1", "true", "yes", "on"}

CODEX_ROOT_ENV_NAMES = (
    "AICARMINE_CODEX_MCP_REPO_ROOT",
    "CODEX_WORKSPACE_ROOT",
    "CODEX_PROJECT_ROOT",
    "CODEX_CWD",
    "WORKSPACE_ROOT",
    "PROJECT_ROOT",
    "INIT_CWD",
    "PWD",
)

Handler = Callable[[dict[str, Any], Path], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    required_one_of: list[list[str]] = field(default_factory=list)


def log(server_name: str, message: str) -> None:
    if DEBUG:
        print(f"[{server_name}] {message}", file=sys.stderr, flush=True)


def json_dumps(value: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def json_compress(value: Any) -> str:
    """Compress JSON payload using bz2 for large responses. Replaces per-server duplicates."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    compressed = bz2.compress(raw.encode("utf-8"))
    return compressed.hex()


def json_decompress(hex_data: str) -> Any:
    """Decompress bz2-compressed JSON payload. Returns parsed JSON."""
    raw = bz2.decompress(bytes.fromhex(hex_data))
    return json.loads(raw.decode("utf-8"))


def smart_json_dumps(value: Any, *, use_compression: bool | None = None) -> str:
    """Smart JSON serialization: compresses if payload exceeds threshold. Replaces per-server duplicates."""
    if use_compression is None:
        use_compression = COMPRESSION_ENABLED
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if use_compression and len(raw) > 10000:
        return f"__compressed__:{json_compress(value)}"
    return raw


def compact_text(value: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        return json_dumps(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 170)].rstrip() + "\n\n...[truncated by aicarmine_repo_mcp]"


def tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    """MCP tool content wrapper with optional bz2 compression for large payloads."""
    text = compact_text(value)
    # Compress if payload exceeds threshold and compression is enabled
    if COMPRESSION_ENABLED and len(text.encode("utf-8")) > 10000:
        compressed = json_compress(value)
        text = f"__compressed__:{compressed}"
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def decompress_tool_text(text: str) -> str:
    """Decompress bz2-compressed MCP tool text. Returns original or decompressed text."""
    if isinstance(text, str) and text.startswith("__compressed__:"):
        hex_data = text[len("__compressed__:"):]
        try:
            return json_decompress(hex_data)
        except Exception:
            return text  # Return original if decompression fails
    return text


def ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def path_git_root(candidate: Path) -> Path | None:
    try:
        current = candidate.expanduser().resolve()
    except Exception:
        return None
    if current.is_file():
        current = current.parent
    for item in [current, *current.parents]:
        if (item / ".git").exists():
            return item
    return None


def env_existing_root(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.exists():
        return None
    return path_git_root(candidate) or candidate.resolve()


def selected_repo_root() -> Path:
    for name in CODEX_ROOT_ENV_NAMES:
        root = env_existing_root(name)
        if root is not None:
            return root

    cwd = Path(os.getcwd())
    cwd_git_root = path_git_root(cwd)
    if cwd_git_root is not None:
        return cwd_git_root

    legacy_lab_root = env_existing_root("AICARMINE_LAB_REPO")
    if legacy_lab_root is not None:
        return legacy_lab_root

    return cwd.resolve()


def selected_repo_root_source(root: Path | None = None) -> str:
    resolved = root or selected_repo_root()
    for name in CODEX_ROOT_ENV_NAMES:
        env_root = env_existing_root(name)
        if env_root is not None and env_root == resolved:
            return name

    cwd = Path(os.getcwd())
    cwd_git_root = path_git_root(cwd)
    if cwd_git_root is not None and cwd_git_root == resolved:
        return "cwd_git_root"

    legacy_lab_root = env_existing_root("AICARMINE_LAB_REPO")
    if legacy_lab_root is not None and legacy_lab_root == resolved:
        return "AICARMINE_LAB_REPO"

    return "cwd_fallback"


def sync_broker_import_root() -> Path:
    root = selected_repo_root()
    root_text = str(root)
    os.environ["AICARMINE_CODEX_MCP_REPO_ROOT"] = root_text
    os.environ["AICARMINE_LAB_REPO"] = root_text
    return root


sync_broker_import_root()


def run_git(root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_info(root: Path) -> dict[str, Any]:
    top_code, top, top_err = run_git(root, "rev-parse", "--show-toplevel")
    branch_code, branch, branch_err = run_git(root, "branch", "--show-current")
    commit_code, commit, commit_err = run_git(root, "rev-parse", "--short", "HEAD")
    return {
        "git_root": top,
        "git_root_ok": top_code == 0 and Path(top).resolve() == root if top else False,
        "branch": branch if branch_code == 0 else "",
        "commit": commit if commit_code == 0 else "",
        "errors": {
            "root": top_err if top_code != 0 else "",
            "branch": branch_err if branch_code != 0 else "",
            "commit": commit_err if commit_code != 0 else "",
        },
    }


def health_payload(server_name: str, tool_names: list[str]) -> dict[str, Any]:
    root = selected_repo_root()
    git = git_info(root)
    ok_value = root.exists() and (root / ".git").exists() and bool(git.get("git_root_ok"))
    return {
        "ok": ok_value,
        "server": server_name,
        "python_executable": sys.executable,
        "python_version": sys.version,
        "repo_root": str(root),
        "root_source": selected_repo_root_source(root),
        "cwd": str(Path.cwd()),
        "aicarmine_lab_repo": os.environ.get("AICARMINE_LAB_REPO", ""),
        "initial_aicarmine_lab_repo": INITIAL_AICARMINE_LAB_REPO,
        "codex_mcp_repo_root": os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT", ""),
        "git_root_ok": git.get("git_root_ok"),
        "branch": git.get("branch"),
        "commit": git.get("commit"),
        "tools": tool_names,
        "no_broker_http": True,
        "no_agentic_loop": True,
    }


def read_message(stdin: BinaryIO) -> dict[str, Any] | None:
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


def write_message(stdout: BinaryIO, payload: dict[str, Any]) -> None:
    raw = json_dumps(payload, compact=True).encode("utf-8")
    if STDIO_TRANSPORT == "content-length":
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
    else:
        stdout.write(raw + b"\n")
    stdout.flush()


def tool_list_payload(tools: dict[str, ToolSpec]) -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            }
            for spec in tools.values()
        ]
    }


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _matches_json_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "null":
        return value is None
    return True


def _type_names(schema_type: Any) -> list[str]:
    if isinstance(schema_type, str):
        return [schema_type]
    if isinstance(schema_type, list):
        return [str(item) for item in schema_type if isinstance(item, str)]
    return []


def _validate_property(tool: str, name: str, value: Any, schema: dict[str, Any]) -> dict[str, Any] | None:
    type_names = _type_names(schema.get("type"))
    if type_names and not any(_matches_json_type(value, type_name) for type_name in type_names):
        return {
            "ok": False,
            "error": "invalid_argument_type",
            "tool": tool,
            "argument": name,
            "expected": type_names[0] if len(type_names) == 1 else type_names,
            "actual": type(value).__name__,
        }
    if schema.get("type") == "array" and isinstance(value, list):
        raw_item_schema = schema.get("items")
        item_schema = raw_item_schema if isinstance(raw_item_schema, dict) else {}
        item_types = _type_names(item_schema.get("type"))
        if item_types:
            for idx, item in enumerate(value):
                if not any(_matches_json_type(item, type_name) for type_name in item_types):
                    return {
                        "ok": False,
                        "error": "invalid_argument_item_type",
                        "tool": tool,
                        "argument": name,
                        "index": idx,
                        "expected": item_types[0] if len(item_types) == 1 else item_types,
                        "actual": type(item).__name__,
                    }
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return {"ok": False, "error": "argument_below_minimum", "tool": tool, "argument": name, "minimum": schema["minimum"], "actual": value}
        if "maximum" in schema and value > schema["maximum"]:
            return {"ok": False, "error": "argument_above_maximum", "tool": tool, "argument": name, "maximum": schema["maximum"], "actual": value}
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values and value not in enum_values:
        return {"ok": False, "error": "invalid_argument_value", "tool": tool, "argument": name, "allowed": enum_values, "actual": value}
    return None


def validate_arguments(spec: ToolSpec, arguments: Any) -> dict[str, Any] | None:
    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "error": "invalid_arguments",
            "tool": spec.name,
            "expected": "object",
            "actual": type(arguments).__name__,
        }
    schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
    raw_properties = schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, dict) else {}
    raw_required = schema.get("required")
    required = raw_required if isinstance(raw_required, list) else []
    missing = [str(name) for name in required if not _has_value(arguments.get(str(name)))]
    if missing:
        return {"ok": False, "error": "missing_required_arguments", "tool": spec.name, "missing": missing}
    required_groups = [
        [str(name) for name in group]
        for group in spec.required_one_of
    ]
    if required_groups and not any(all(_has_value(arguments.get(name)) for name in group) for group in required_groups):
        return {
            "ok": False,
            "error": "missing_required_argument_group",
            "tool": spec.name,
            "requires_one_of": required_groups,
        }
    for name, value in arguments.items():
        prop = properties.get(name)
        if isinstance(prop, dict):
            problem = _validate_property(spec.name, str(name), value, prop)
            if problem is not None:
                return problem
    return None


def result_is_error(result: Any) -> bool:
    return bool(isinstance(result, dict) and (result.get("is_error") or result.get("ok") is False))


def _diagnostic_context() -> dict[str, Any]:
    """Return diagnostic context for error reporting."""
    root = selected_repo_root()
    git = git_info(root)
    return {
        "repo_root": str(root),
        "root_source": selected_repo_root_source(root),
        "cwd": str(Path.cwd()),
        "git_root_ok": git.get("git_root_ok"),
        "branch": git.get("branch"),
        "commit": git.get("commit"),
        "python_executable": sys.executable,
        "python_version": sys.version.split("\n")[0],
    }


def call_tool(tools: dict[str, ToolSpec], name: str, arguments: Any) -> dict[str, Any]:
    spec = tools.get(name)
    if spec is None:
        return tool_content({"ok": False, "error": "unknown_tool", "tool": name}, is_error=True)
    argument_error = validate_arguments(spec, arguments)
    if argument_error is not None:
        return tool_content(argument_error, is_error=True)
    try:
        root = selected_repo_root()
        result = spec.handler(arguments, root)
        return tool_content(result, is_error=result_is_error(result))
    except Exception as exc:
        ctx = _diagnostic_context()
        error_payload = {
            "ok": False,
            "error": "tool_call_failed",
            "tool": name,
            "error_type": type(exc).__name__,
            "message": str(exc)[:2000],
            "traceback": traceback.format_exc()[-4000:],
            "diagnostic_context": ctx,
        }
        return tool_content(error_payload, is_error=True)


def handle_request(
    request: dict[str, Any],
    *,
    server_name: str,
    server_version: str,
    tools: dict[str, ToolSpec],
) -> dict[str, Any] | None:
    method = str(request.get("method") or "")
    msg_id = request.get("id")
    raw_params = request.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}

    if method == "initialize":
        return ok(
            msg_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": server_version},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok(msg_id, tool_list_payload(tools))
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        return ok(msg_id, call_tool(tools, name, arguments))
    if method == "ping":
        return ok(msg_id, {})
    return err(msg_id, -32601, f"method_not_found: {method}")


def serve(server_name: str, server_version: str, tools: dict[str, ToolSpec]) -> int:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        request = read_message(stdin)
        if request is None:
            return 0
        response = handle_request(
            request,
            server_name=server_name,
            server_version=server_version,
            tools=tools,
        )
        if response is not None:
            write_message(stdout, response)


# ── Extended MCP handlers with resources/prompts/roots (replaces mcp_server.py _handle_rpc) ──


def mcp_handle_request_extended(
    request: dict[str, Any],
    *,
    server_name: str,
    server_version: str,
    tools: list[dict[str, Any]],
    tools_call_handler: Callable[[str, dict[str, Any]], Any],
    resources_list_handler: Callable[[dict[str, Any]], dict[str, Any]],
    resources_read_handler: Callable[[dict[str, Any]], dict[str, Any]],
    roots_list_handler: Callable[[dict[str, Any]], dict[str, Any]],
    instructions: str | None = None,
) -> dict[str, Any] | None:
    """
    Handle one JSON-RPC message for servers with resources/prompts/roots support.

    Replaces identical _handle_rpc() from mcp_server.py (~100 lines).
    Supports: initialize, ping, tools/list, tools/call, resources/list,
              resources/read, roots/list, notifications/*, logging/setLevel.
    
    Args:
        instructions: Optional server instructions included in initialize response.
    """
    method = str(request.get("method") or "")
    msg_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        response_data: dict[str, Any] = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
                "roots": {"listChanged": False},
                "completion": {},
            },
            "serverInfo": {"name": server_name, "version": server_version},
        }
        if instructions:
            response_data["instructions"] = instructions
        return ok(msg_id, response_data)
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return ok(msg_id, {})
    if method == "tools/list":
        return ok(msg_id, {"tools": tools})
    if method == "tools/call":
        name = params.get("name", "")
        tool_args = params.get("arguments", {})
        result = tools_call_handler(name, tool_args)
        return ok(msg_id, result)
    if method == "resources/list":
        return ok(msg_id, resources_list_handler(params))
    if method == "resources/read":
        return ok(msg_id, resources_read_handler(params))
    if method == "roots/list":
        return ok(msg_id, roots_list_handler(params))
    if method == "logging/setLevel":
        return ok(msg_id, {})
    if method.startswith("notifications/"):
        return None
    return err(msg_id, -32601, f"method_not_found: {method}")


def mcp_serve_extended(
    stdin: BinaryIO,
    stdout: BinaryIO,
    *,
    server_name: str,
    server_version: str,
    tools: list[dict[str, Any]],
    tools_call_handler: Callable[[str, dict[str, Any]], Any],
    resources_list_handler: Callable[[dict[str, Any]], dict[str, Any]],
    resources_read_handler: Callable[[dict[str, Any]], dict[str, Any]],
    roots_list_handler: Callable[[dict[str, Any]], dict[str, Any]],
    instructions: str | None = None,
) -> int:
    """
    Main serve loop for servers with resources/prompts/roots support.

    Replaces identical serve() from mcp_server.py (~15 lines).
    """
    while True:
        first = stdin.readline()
        if not first:
            return 0
        decoded = first.decode("utf-8-sig", errors="replace").strip()
        if decoded:
            break

    if decoded.startswith("{"):
        request = json.loads(decoded)
    else:
        headers: dict[str, str] = {}
        while True:
            line = stdin.readline()
            if not line:
                return 0
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded == "":
                break
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = stdin.read(length)
        request = json.loads(body.decode("utf-8-sig", errors="replace"))

    response = mcp_handle_request_extended(
        request,
        server_name=server_name,
        server_version=server_version,
        tools=tools,
        tools_call_handler=tools_call_handler,
        resources_list_handler=resources_list_handler,
        resources_read_handler=resources_read_handler,
        roots_list_handler=roots_list_handler,
        instructions=instructions,
    )
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
        stdout.flush()

    return 0


# ── End of extended MCP handlers ──
def mcp_text_result(response: dict[str, Any]) -> dict[str, Any]:
    raw_result = response.get("result")
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_content = result.get("content")
    content = raw_content if isinstance(raw_content, list) else []
    first = content[0] if content and isinstance(content[0], dict) else {}
    text = first.get("text")
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {"_raw_text": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def self_test(
    *,
    server_name: str,
    server_version: str,
    tools: dict[str, ToolSpec],
    health_tool: str,
    real_tool: str,
    real_args: dict[str, Any],
) -> dict[str, Any]:
    init = handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        server_name=server_name,
        server_version=server_version,
        tools=tools,
    )
    listed = handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        server_name=server_name,
        server_version=server_version,
        tools=tools,
    )
    health = handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": health_tool, "arguments": {}}},
        server_name=server_name,
        server_version=server_version,
        tools=tools,
    )
    real = handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": real_tool, "arguments": real_args}},
        server_name=server_name,
        server_version=server_version,
        tools=tools,
    )
    raw_list_result = listed.get("result") if isinstance(listed, dict) else {}
    list_result = raw_list_result if isinstance(raw_list_result, dict) else {}
    listed_names = [
        item.get("name")
        for item in list_result.get("tools", [])
        if isinstance(item, dict)
    ]
    health_payload_value = mcp_text_result(health if isinstance(health, dict) else {})
    real_payload_value = mcp_text_result(real if isinstance(real, dict) else {})
    ok_value = bool(
        init
        and "error" not in init
        and health_payload_value.get("ok") is True
        and health_tool in listed_names
        and real_tool in listed_names
        and isinstance(real_payload_value, dict)
        and real_payload_value.get("tool")
        and real_payload_value.get("ok") is True
    )
    return {
        "ok": ok_value,
        "server": server_name,
        "initialize_ok": bool(init and "error" not in init),
        "tools_list_ok": bool(health_tool in listed_names and real_tool in listed_names),
        "tool_count": len(listed_names),
        "health": health_payload_value,
        "real_tool": {
            "name": real_tool,
            "ok": real_payload_value.get("ok"),
            "tool": real_payload_value.get("tool"),
            "error": real_payload_value.get("error"),
            "returncode": real_payload_value.get("returncode"),
        },
    }


def object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


# ── Shared schema builders (replaces per-server duplicates) ──────────────

def string_prop(default: str | None = None) -> dict[str, Any]:
    """Build a JSON Schema string property. Compatible with all server variants."""
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    """Build a JSON Schema array-of-strings property. Replaces per-server duplicates."""
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    """Build a JSON Schema integer property. Compatible with all server variants."""
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    """Build a JSON Schema boolean property. Compatible with all server variants."""
    return {"type": "boolean", "default": default}


def string_prop_with_enum(
    default: str | None = None, *, enum: list[str] | None = None
) -> dict[str, Any]:
    """Build a JSON Schema string property with optional enum constraint. Replaces per-server duplicates."""
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if enum is not None:
        schema["enum"] = enum


# ── Shared generic helpers (from mcp_server.py, reused by aicarmine_codex_mcp_server) ──


def _json_dumps(value: Any) -> str:
    """JSON dumps with ensure_ascii=False and indent=2. Replaces per-server duplicates."""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def compact_text_generic(value: Any, limit: int = MAX_TEXT) -> str:
    """Compact a value to string with truncation. Replaces 6 identical _compact_text implementations."""
    text = value if isinstance(value, str) else _json_dumps(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 180)].rstrip() + "\n\n...[truncated]"


def compact_text_tuple(value: Any, max_chars: int, server_name: str = "repo_mcp") -> tuple[str, bool]:
    """Compact text returning (text, truncated_bool). Replaces agentic_loop_client variant."""
    text = value if isinstance(value, str) else _json_dumps(value)
    if len(text) <= max_chars:
        return text, False
    suffix = f"\n...[truncated by {server_name}]"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix, True


def _diagnostic_preview(value: Any, limit: int = 500) -> str:
    """Diagnostic preview for error messages. Replaces per-server duplicates."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        try:
            text = str(value)
        except Exception:
            text = f"<unprintable {type(value).__name__}>"
    return text[:limit]


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    """MCP tool content wrapper. Replaces per-server duplicates."""
    return {"content": [{"type": "text", "text": compact_text_generic(value)}], "isError": is_error}


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    """JSON-RPC 2.0 success response. Replaces per-server duplicates."""
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """JSON-RPC 2.0 error response. Replaces per-server duplicates."""
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def safe_int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    """Safe integer conversion with clamping. Replaces per-server duplicates."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def _safe_int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    """Alias for callers that expect `_safe_int` name."""
    return safe_int(value, default, low, high)


def read_tail(path: Path, max_lines: int, max_bytes: int) -> str:
    """Read tail of a file with line/byte limits. Replaces ops_mcp_server _read_tail."""
    try:
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    selected = lines[-max_lines:] if len(lines) > max_lines else lines
    text = "\n".join(selected)
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    while len(text.encode("utf-8")) > max_bytes and text:
        text = text[:-1]
    return text.rstrip()


def _read_tail(path: Path, max_lines: int = 200, max_bytes: int = 4000) -> str:
    """Alias for callers that expect `_read_tail` name."""
    return read_tail(path, max_lines, max_bytes)


def path_is_under(path: Path, parent: Path) -> bool:
    """Check if path is under parent directory. Replaces per-server duplicates."""
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def diagnostic_preview(value: Any, limit: int = 500) -> str:
    """Public alias for _diagnostic_preview."""
    return _diagnostic_preview(value, limit)
    return schema


def object_prop() -> dict[str, Any]:
    """Build a JSON Schema object property with additionalProperties=True. Replaces per-server duplicates."""
    return {"type": "object", "additionalProperties": True}


# ── Shared safe converters (replaces per-server duplicates) ──────────────

def safe_int(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    """Safely convert to int with optional clamping. Compatible with all server variants."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if low is not None and high is not None:
        return max(low, min(high, number))
    return number


def safe_float(value: Any, default: float = 0.0, low: float | None = None, high: float | None = None) -> float:
    """Safely convert to float with optional clamping."""
    try:
        result = float(value)
    except (ValueError, TypeError):
        result = default
    if low is not None and high is not None:
        return max(low, min(high, result))
    return result


def safe_bool(value: Any, default: bool = False) -> bool:
    """Safely convert to bool. Handles str/int/bool inputs."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value) if default else False


# ── Shared json helpers (replaces per-server duplicates) ─────────────────

def json_text(value: Any) -> str:
    """JSON serialization with indent=2. Compatible with _json_text variants."""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def json_path_select(value: Any, path: str) -> tuple[Any, str]:
    """Select a sub-element from JSON structure by dot-path. Returns (value, normalized_path)."""
    current = value
    normalized = str(path or "").strip().strip(".")
    if not normalized:
        return current, ""
    traversed: list[str] = []
    for part in normalized.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(".".join([*traversed, part]))
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise KeyError(".".join([*traversed, part])) from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise KeyError(".".join([*traversed, part])) from exc
        else:
            raise KeyError(".".join([*traversed, part]))
        traversed.append(part)
    return current, ".".join(traversed)


# ── Shared path helpers (replaces per-server duplicates) ─────────────────

def path_is_under(child: Path, parent: Path) -> bool:
    """Check if child path is under parent path. Replaces 4 identical implementations."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# ── Shared text preview helpers (replaces per-server duplicates) ──────────

def diagnostic_preview(value: Any, limit: int = 500) -> str:
    """Preview a value as JSON with truncation. Replaces 4 identical implementations."""
    if isinstance(value, str):
        return value[:limit] if len(value) > limit else value
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return text[:limit] if len(text) > limit else text
    except Exception:
        return str(value)[:limit]


# ── Shared compact_text helpers (replaces 8 per-server duplicates) ─────────

def compact_text_generic(value: Any, limit: int = MAX_TEXT) -> str:
    """Compact a value to string with truncation. Replaces 6 identical _compact_text implementations."""
    if not isinstance(value, str):
        return json_dumps(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 170)].rstrip() + "\n\n...[truncated by aicarmine_repo_mcp]"


def compact_text_tuple(value: Any, max_chars: int) -> tuple[str, bool]:
    """Compact text returning (text, truncated_bool). Replaces agentic_loop_client variant."""
    if not isinstance(value, str):
        text = json_dumps(value)
    else:
        text = value
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return text, truncated


def read_tail(path: Path, max_lines: int, max_bytes: int) -> str:
    """Read tail of a file with line/byte limits. Replaces ops_mcp_server _read_tail."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, os.SEEK_END)
        raw = handle.read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


# ── Shared MCP request handler and serve loop (replaces 6 per-server duplicates) ──


def mcp_handle_request(
    request: dict[str, Any],
    *,
    server_name: str,
    server_version: str,
    tools: dict[str, dict[str, Any]],
    handlers: dict[str, Any],
    root: Path,
) -> dict[str, Any] | None:
    """
    Handle one JSON-RPC message for CLI tool MCP servers.

    Replaces identical handle_request() from ruff, black, prettier, biome,
    eslint, and clang_format MCP servers (~30 lines each = ~180 lines saved).
    """
    method = str(request.get("method") or "")
    msg_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return ok(
            msg_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": server_version},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok(
            msg_id,
            {
                "tools": [
                    {
                        "name": v["name"],
                        "description": v["description"],
                        "inputSchema": v["inputSchema"],
                    }
                    for v in tools.values()
                ]
            },
        )
    if method == "tools/call":
        name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = handlers.get(name)
        if handler:
            result = handler(tool_args, root)
            return ok(msg_id, result)
        return err(msg_id, -32601, f"unknown_tool: {name}")
    if method == "ping":
        return ok(msg_id, {})
    return err(msg_id, -32601, f"method_not_found: {method}")


def mcp_serve(
    stdin: BinaryIO,
    stdout: BinaryIO,
    *,
    server_name: str,
    server_version: str,
    tools: dict[str, dict[str, Any]],
    handlers: dict[str, Any],
) -> int:
    """
    Main serve loop for CLI tool MCP servers.

    Replaces identical serve() from ruff, black, prettier, biome, eslint,
    and clang_format MCP servers (~45 lines each = ~270 lines saved).

    Returns 0 on normal exit (empty stdin), 1 on error.
    """
    while True:
        first = stdin.readline()
        if not first:
            return 0
        decoded = first.decode("utf-8-sig", errors="replace").strip()
        if decoded:
            break

    if decoded.startswith("{"):
        request = json.loads(decoded)
    else:
        headers: dict[str, str] = {}
        while True:
            line = stdin.readline()
            if not line:
                return 0
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded == "":
                break
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = stdin.read(length)
        request = json.loads(body.decode("utf-8-sig", errors="replace"))

    response = mcp_handle_request(
        request,
        server_name=server_name,
        server_version=server_version,
        tools=tools,
        handlers=handlers,
        root=Path.cwd(),
    )
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
        stdout.flush()

    return 0
