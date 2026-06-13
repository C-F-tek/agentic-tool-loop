#!/usr/bin/env python3
"""Local Ollama-backed read-only subagent MCP server for Codex."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable
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

SERVER_NAME = "aicarmine-local-subagent-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_MODEL = os.environ.get("AICARMINE_LOCAL_SUBAGENT_MODEL", "qwen3.5:9b-coding").strip()
DEFAULT_ENDPOINT = os.environ.get("AICARMINE_LOCAL_SUBAGENT_OLLAMA_URL", "http://127.0.0.1:11434/api/chat").strip()
FORBIDDEN_PORTS = {3571, 3572, 8080, 11435}
RESERVED_TASK_MODEL_RE = re.compile(r"(^gpu0/|qwen3-task|task-8k)", re.IGNORECASE)

LocalToolHandler = Callable[[dict[str, Any], Path], dict[str, Any]]


def string_prop(default: str | None = None, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if enum is not None:
        schema["enum"] = enum
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def number_prop(default: float, minimum: float, maximum: float) -> dict[str, Any]:
    return {"type": "number", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


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
    suffix = f"\n...[truncated chars={len(text)}]"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix, True


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        pass
    except OSError:
        return False
    child_text = str(child.resolve()).lower().rstrip("\\/")
    parent_text = str(parent.resolve()).lower().rstrip("\\/")
    return child_text == parent_text or child_text.startswith(parent_text + "\\") or child_text.startswith(parent_text + "/")


def _repo_path(value: Any, root: Path) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    text = str(value or "").strip()
    if not text:
        return None, None, {"ok": False, "error": "missing_path"}
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return None, None, {"ok": False, "error": "path_resolve_failed", "path": text, "message": str(exc)}
    if not _path_is_under(resolved, root):
        return None, None, {"ok": False, "error": "path_not_under_codex_mcp_repo_root", "path": text, "resolved": str(resolved), "repo_root": str(root)}
    try:
        rel = str(resolved.relative_to(root.resolve()))
    except ValueError:
        rel = str(resolved)
    return resolved, rel, None


def _run_git(root: Path, args: list[str], *, timeout_seconds: int, max_chars: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    stdout, stdout_truncated = _compact_text(proc.stdout, max_chars)
    stderr, stderr_truncated = _compact_text(proc.stderr, max_chars)
    return {
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "command": ["git", "-C", str(root), *args],
    }


def _repo_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path, rel, problem = _repo_path(args.get("path"), root)
    if problem is not None:
        return problem
    assert path is not None and rel is not None
    if not path.is_file():
        return {"ok": False, "error": "file_not_found", "path": rel}
    max_chars = _safe_int(args.get("max_chars"), 20000, 1000, 120000)
    start_line = _safe_int(args.get("start_line"), 1, 1, 1_000_000)
    max_lines = _safe_int(args.get("max_lines"), 400, 1, 4000)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    selected = "\n".join(lines[start_line - 1 : start_line - 1 + max_lines])
    content, truncated = _compact_text(selected, max_chars)
    return {
        "ok": True,
        "tool": "repo_read",
        "path": rel,
        "bytes": path.stat().st_size,
        "start_line": start_line,
        "returned_lines": len(content.splitlines()),
        "content": content,
        "truncated": truncated or len(lines) > start_line - 1 + max_lines,
        "read_only": True,
    }


def _repo_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(args.get("query") or "").strip().lower()
    suffix = str(args.get("suffix") or "").strip().lower()
    limit = _safe_int(args.get("limit") or args.get("max_results"), 200, 1, 2000)
    result = _run_git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"], timeout_seconds=20, max_chars=2_000_000)
    paths: list[str]
    source = "git"
    if result["returncode"] == 0:
        paths = [item for item in str(result["stdout"]).split("\0") if item]
    else:
        source = "filesystem_fallback"
        paths = []
        for item in root.rglob("*"):
            if ".git" in item.parts or not item.is_file():
                continue
            try:
                paths.append(str(item.relative_to(root)))
            except ValueError:
                continue
    filtered = []
    for path in sorted(paths):
        low = path.lower()
        if query and query not in low:
            continue
        if suffix and not low.endswith(suffix):
            continue
        filtered.append(path)
        if len(filtered) >= limit:
            break
    return {"ok": True, "tool": "repo_list_files", "source": source, "query": query, "suffix": suffix, "files": filtered, "count": len(filtered), "limit": limit, "read_only": True}


def _repo_search_rg(args: dict[str, Any], root: Path) -> dict[str, Any]:
    pattern = str(args.get("pattern") or args.get("query") or "").strip()
    if not pattern:
        return {"ok": False, "error": "missing_pattern"}
    search_root, rel, problem = _repo_path(args.get("path") or ".", root)
    if problem is not None:
        return problem
    assert search_root is not None
    rg = shutil.which("rg")
    if rg is None:
        return {"ok": False, "error": "rg_not_found"}
    max_results = _safe_int(args.get("max_results") or args.get("limit"), 80, 1, 1000)
    context = _safe_int(args.get("context"), 0, 0, 5)
    timeout_seconds = _safe_int(args.get("timeout_seconds"), 30, 1, 120)
    cmd = [rg, "--json", "--line-number", "--no-heading"]
    if context:
        cmd.extend(["--context", str(context)])
    cmd.extend(["--", pattern, str(search_root)])
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
    matches: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if len(matches) >= max_results:
            break
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") != "match":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        path_text = str(data.get("path", {}).get("text", ""))
        try:
            display_path = str(Path(path_text).resolve().relative_to(root.resolve()))
        except (OSError, ValueError):
            display_path = path_text
        raw_lines = data.get("lines")
        lines = raw_lines if isinstance(raw_lines, dict) else {}
        matches.append({"path": display_path, "line_number": data.get("line_number"), "text": str(lines.get("text", "")).rstrip("\r\n")})
    return {"ok": proc.returncode in {0, 1}, "tool": "repo_search_rg", "path": rel or ".", "pattern": pattern, "matches": matches, "count": len(matches), "truncated": len(matches) >= max_results, "returncode": proc.returncode, "stderr_tail": proc.stderr[-2000:], "read_only": True}


def _git_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
    max_chars = _safe_int(args.get("max_chars"), 80000, 1000, 500000)
    timeout_seconds = _safe_int(args.get("timeout_seconds"), 20, 1, 120)
    pathspec = None
    if str(args.get("path") or "").strip():
        _path, rel, problem = _repo_path(args.get("path"), root)
        if problem is not None:
            return problem
        pathspec = rel
    cmd = ["diff", "--no-ext-diff"]
    if _safe_bool(args.get("staged"), False):
        cmd.append("--staged")
    if pathspec:
        cmd.extend(["--", pathspec])
    result = _run_git(root, cmd, timeout_seconds=timeout_seconds, max_chars=max_chars)
    return {"ok": result["returncode"] == 0, "tool": "git_diff", "git": result, "read_only": True}


def _memory_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    from project_memory_mcp_server import _search  # noqa: PLC0415

    forwarded = {
        "query": str(args.get("query") or ""),
        "scope": str(args.get("scope") or ""),
        "status": str(args.get("status") or "active"),
        "include_stale": _safe_bool(args.get("include_stale"), False),
        "limit": _safe_int(args.get("limit") or args.get("max_results"), 10, 1, 50),
    }
    result = _search(forwarded, root)
    result["proxied_by"] = "aicarmine_local_subagent"
    result["read_only"] = True
    return result


def _rag_context(args: dict[str, Any], root: Path) -> dict[str, Any]:
    from rag_mcp_server import _handle_context_tool  # noqa: PLC0415

    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing_query"}
    forwarded = {
        "query": query,
        "repo": str(root),
        "top_k": _safe_int(args.get("top_k"), 5, 1, 20),
        "candidate_limit": _safe_int(args.get("candidate_limit"), 80, 1, 200),
        "max_total_chars": _safe_int(args.get("max_total_chars"), 12000, 1000, 80000),
        "max_chunk_chars": _safe_int(args.get("max_chunk_chars"), 4000, 500, 20000),
        "rerank": _safe_bool(args.get("rerank"), False),
    }
    result = _handle_context_tool(forwarded)
    result["proxied_by"] = "aicarmine_local_subagent"
    result["read_only"] = True
    return result


LOCAL_TOOL_HANDLERS: dict[str, LocalToolHandler] = {
    "repo_read": _repo_read,
    "repo_list_files": _repo_list_files,
    "repo_search_rg": _repo_search_rg,
    "git_diff": _git_diff,
    "memory_search": _memory_search,
    "rag_context": _rag_context,
}

LOCAL_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "repo_read": {
        "description": "Read a repo-relative text file under the Codex MCP repo root.",
        "parameters": object_schema({"path": string_prop(), "start_line": integer_prop(1, 1, 1_000_000), "max_lines": integer_prop(400, 1, 4000), "max_chars": integer_prop(20000, 1000, 120000)}, required=["path"]),
    },
    "repo_list_files": {
        "description": "List tracked and untracked non-ignored files under the Codex MCP repo root.",
        "parameters": object_schema({"query": string_prop(), "suffix": string_prop(), "limit": integer_prop(200, 1, 2000)}),
    },
    "repo_search_rg": {
        "description": "Search repo text with ripgrep under the Codex MCP repo root.",
        "parameters": object_schema({"pattern": string_prop(), "path": string_prop("."), "max_results": integer_prop(80, 1, 1000), "context": integer_prop(0, 0, 5)}, required=["pattern"]),
    },
    "git_diff": {
        "description": "Read bounded git diff output. Never stages, commits, checks out, fetches or pushes.",
        "parameters": object_schema({"path": string_prop(), "staged": boolean_prop(False), "max_chars": integer_prop(80000, 1000, 500000)}),
    },
    "memory_search": {
        "description": "Search active project-local persistent memory records.",
        "parameters": object_schema({"query": string_prop(), "scope": string_prop(), "status": string_prop("active"), "include_stale": boolean_prop(False), "limit": integer_prop(10, 1, 50)}),
    },
    "rag_context": {
        "description": "Search the Codex RAG index for code context. Rerank defaults off to avoid GPU contention.",
        "parameters": object_schema({"query": string_prop(), "top_k": integer_prop(5, 1, 20), "candidate_limit": integer_prop(80, 1, 200), "max_total_chars": integer_prop(12000, 1000, 80000), "rerank": boolean_prop(False)}, required=["query"]),
    },
}


def _allowed_local_tools(args: dict[str, Any] | None = None) -> list[str]:
    args = args or {}
    raw = args.get("allowed_tools")
    requested = [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []
    names = requested or list(LOCAL_TOOL_HANDLERS)
    return [name for name in names if name in LOCAL_TOOL_HANDLERS]


def _ollama_tool_definitions(tool_names: list[str]) -> list[dict[str, Any]]:
    definitions = []
    for name in tool_names:
        spec = LOCAL_TOOL_DEFINITIONS[name]
        definitions.append({"type": "function", "function": {"name": name, "description": spec["description"], "parameters": spec["parameters"]}})
    return definitions


def _validate_model(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    model = str(value or DEFAULT_MODEL).strip()
    if not model:
        return None, {"ok": False, "error": "missing_model"}
    if RESERVED_TASK_MODEL_RE.search(model):
        return None, {"ok": False, "error": "reserved_task_model_rejected", "model": model, "reason": "11435/GPU0 task models are reserved for task/repair/rerank lanes; local subagent must use the large 11434 model."}
    return model, None


def _validate_ollama_endpoint(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    raw = str(value or DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    parsed = urllib.parse.urlparse(raw)
    if not parsed.scheme:
        parsed = urllib.parse.urlparse(f"http://{raw}")
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port or (80 if scheme == "http" else 443)
    if scheme != "http" or host not in {"127.0.0.1", "localhost"} or port != 11434:
        return None, {"ok": False, "error": "ollama_endpoint_not_allowlisted", "endpoint": raw, "allowed": ["http://127.0.0.1:11434/api/chat"], "forbidden_ports": sorted(FORBIDDEN_PORTS)}
    path = parsed.path.rstrip("/") or "/api/chat"
    if path != "/api/chat":
        return None, {"ok": False, "error": "unsupported_ollama_path", "endpoint": raw, "required_path": "/api/chat"}
    normalized = urllib.parse.urlunparse(("http", f"{host}:{port}", "/api/chat", "", "", ""))
    return normalized, None


def _ollama_tags_url(chat_endpoint: str) -> str:
    parsed = urllib.parse.urlparse(chat_endpoint)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/api/tags", "", "", ""))


def _ollama_chat(endpoint: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _ollama_tags(endpoint: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(_ollama_tags_url(endpoint), method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _parse_tool_call(raw: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return "", {}
    raw_function = raw.get("function")
    function = raw_function if isinstance(raw_function, dict) else raw
    name = str(function.get("name") or "").strip()
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return name, arguments


def _system_prompt(root: Path, tool_names: list[str]) -> str:
    return (
        "You are a local read-only Codex subagent running through an MCP wrapper.\n"
        f"Codex MCP repo root: {root}\n"
        "Use only the provided read-only tools. Do not claim you inspected a file unless a tool returned its content.\n"
        "Never request writes, apply patches, start services, call OpenWebUI, call 3571/3572, call 11435, or use shell commands.\n"
        "RAG rerank is off unless explicitly needed; prefer precise searches and bounded reads.\n"
        "Return a concise answer with evidence paths and limitations. Allowed tools: "
        + ", ".join(tool_names)
    )


def _run_local_tool(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    handler = LOCAL_TOOL_HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": "local_subagent_tool_not_allowlisted", "tool": name}
    try:
        return handler(arguments, root)
    except Exception as exc:
        return {"ok": False, "error": "local_subagent_tool_failed", "tool": name, "error_type": type(exc).__name__, "message": str(exc)}


def _run_readonly(args: dict[str, Any], root: Path) -> dict[str, Any]:
    task = str(args.get("task") or "").strip()
    if not task:
        return {"ok": False, "error": "missing_task"}
    endpoint, endpoint_problem = _validate_ollama_endpoint(args.get("endpoint"))
    if endpoint_problem is not None:
        return endpoint_problem
    model, model_problem = _validate_model(args.get("model"))
    if model_problem is not None:
        return model_problem
    assert endpoint is not None and model is not None

    tool_names = _allowed_local_tools(args)
    max_tool_rounds = _safe_int(args.get("max_tool_rounds"), 4, 0, 8)
    timeout_seconds = _safe_int(args.get("timeout_seconds"), 120, 5, 600)
    num_ctx = _safe_int(args.get("num_ctx"), 262144, 2048, 262144)
    temperature = _safe_float(args.get("temperature"), 0.1, 0.0, 2.0)
    include_tool_transcript = _safe_bool(args.get("include_tool_transcript"), True)
    initial_context, initial_context_truncated = _compact_text(str(args.get("initial_context") or "").strip(), 50000)

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(root, tool_names)}]
    user_content = task
    if initial_context:
        user_content += "\n\nInitial verified context:\n" + initial_context
    messages.append({"role": "user", "content": user_content})
    tool_transcript: list[dict[str, Any]] = []
    final_message: dict[str, Any] = {}

    try:
        for round_index in range(max_tool_rounds + 1):
            payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_ctx": num_ctx}}
            if round_index < max_tool_rounds and tool_names:
                payload["tools"] = _ollama_tool_definitions(tool_names)
            response = _ollama_chat(endpoint, payload, timeout_seconds)
            raw_message = response.get("message")
            message = raw_message if isinstance(raw_message, dict) else {}
            final_message = message
            assistant_message: dict[str, Any] = {"role": "assistant", "content": str(message.get("content") or "")}
            raw_tool_calls = message.get("tool_calls")
            tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) else []
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            if not tool_calls or round_index >= max_tool_rounds:
                break
            for raw_call in tool_calls:
                tool_name, tool_args = _parse_tool_call(raw_call)
                tool_result = _run_local_tool(tool_name, tool_args, root) if tool_name in tool_names else {"ok": False, "error": "tool_not_in_local_subagent_surface", "tool": tool_name}
                compact_result, result_truncated = _compact_text(tool_result, 30000)
                messages.append({"role": "tool", "tool_name": tool_name, "content": compact_result})
                tool_transcript.append({"round": round_index + 1, "tool": tool_name, "arguments": tool_args, "ok": bool(isinstance(tool_result, dict) and tool_result.get("ok") is True), "result_truncated": result_truncated, "result": tool_result if include_tool_transcript and not result_truncated else compact_result})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": "ollama_chat_failed", "endpoint": endpoint, "model": model, "error_type": type(exc).__name__, "message": str(exc), "hint": "Verify Ollama is listening on 127.0.0.1:11434. This tool never starts 11435 or local services."}

    return {
        "ok": True,
        "tool": "aicarmine_local_subagent_run_readonly",
        "endpoint": endpoint,
        "model": model,
        "repo_root": str(root),
        "initial_aicarmine_lab_repo": os.environ.get("AICARMINE_LAB_REPO", ""),
        "codex_mcp_repo_root": os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT", ""),
        "root_isolation": "Codex MCP root is process-local and does not call or reconfigure 3572 agentic loop roots.",
        "forbidden_ports": sorted(FORBIDDEN_PORTS),
        "allowed_tools": tool_names,
        "tool_round_limit": max_tool_rounds,
        "tool_call_count": len(tool_transcript),
        "initial_context_truncated": initial_context_truncated,
        "response": str(final_message.get("content") or ""),
        "tool_transcript": tool_transcript if include_tool_transcript else [],
        "read_only": True,
        "no_broker_http": True,
        "no_agentic_loop": True,
    }


def _capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del args
    return {
        "ok": True,
        "tool": "aicarmine_local_subagent_capabilities",
        "repo_root": str(root),
        "model_default": DEFAULT_MODEL,
        "endpoint_default": DEFAULT_ENDPOINT,
        "endpoint_policy": {"allowed": ["http://127.0.0.1:11434/api/chat", "http://localhost:11434/api/chat"], "forbidden_ports": sorted(FORBIDDEN_PORTS), "rejects_gpu0_task_models": True},
        "local_subagent_tools": [{"name": name, "description": LOCAL_TOOL_DEFINITIONS[name]["description"]} for name in LOCAL_TOOL_HANDLERS],
        "codex_app_subagents_inherited": False,
        "codex_app_subagents_note": "Codex /subagents are app-level agents. This MCP replicates a read-only subset through explicit local handlers.",
        "write_tools": [],
        "read_only": True,
        "no_broker_http": True,
        "no_agentic_loop": True,
    }


def _tool_surface(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del root
    tool_names = _allowed_local_tools(args)
    return {"ok": True, "tool": "aicarmine_local_subagent_tool_surface", "tool_names": tool_names, "ollama_tools": _ollama_tool_definitions(tool_names), "read_only": True}


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    endpoint, endpoint_problem = _validate_ollama_endpoint(args.get("endpoint"))
    model, model_problem = _validate_model(args.get("model"))
    payload.update(
        {
            "tool": "aicarmine_local_subagent_health",
            "endpoint": endpoint or DEFAULT_ENDPOINT,
            "endpoint_ok": endpoint_problem is None,
            "endpoint_problem": endpoint_problem,
            "model": model or DEFAULT_MODEL,
            "model_ok": model_problem is None,
            "model_problem": model_problem,
            "root_isolation": {"codex_mcp_repo_root": os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT", ""), "effective_mcp_lab_repo": os.environ.get("AICARMINE_LAB_REPO", ""), "note": "AICARMINE_LAB_REPO is rewritten only inside this MCP process before local tool imports."},
            "forbidden_ports": sorted(FORBIDDEN_PORTS),
            "read_only": True,
            "does_not_start_ollama": True,
        }
    )
    if _safe_bool(args.get("probe_ollama"), False) and endpoint_problem is None:
        assert endpoint is not None
        timeout_seconds = _safe_int(args.get("timeout_seconds"), 3, 1, 30)
        try:
            tags = _ollama_tags(endpoint, timeout_seconds)
            raw_models = tags.get("models")
            models = raw_models if isinstance(raw_models, list) else []
            payload["ollama_probe"] = {"ok": True, "tags_url": _ollama_tags_url(endpoint), "model_count": len(models), "models": [item.get("name") for item in models if isinstance(item, dict)][:50]}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            payload["ollama_probe"] = {"ok": False, "error_type": type(exc).__name__, "message": str(exc)}
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_local_subagent_health"] = ToolSpec(
        name="aicarmine_local_subagent_health",
        description="Report local Ollama subagent MCP health, root isolation and 11434-only endpoint policy.",
        input_schema=object_schema({"endpoint": string_prop(DEFAULT_ENDPOINT), "model": string_prop(DEFAULT_MODEL), "probe_ollama": boolean_prop(False), "timeout_seconds": integer_prop(3, 1, 30)}),
        handler=health,
    )
    tools["aicarmine_local_subagent_capabilities"] = ToolSpec(
        name="aicarmine_local_subagent_capabilities",
        description="Describe the read-only local subagent tool surface and Codex app subagent inheritance limits.",
        input_schema=object_schema(),
        handler=_capabilities,
    )
    tools["aicarmine_local_subagent_tool_surface"] = ToolSpec(
        name="aicarmine_local_subagent_tool_surface",
        description="Return the Ollama tool definitions that the local read-only subagent may use.",
        input_schema=object_schema({"allowed_tools": string_array_prop()}),
        handler=_tool_surface,
    )
    tools["aicarmine_local_subagent_run_readonly"] = ToolSpec(
        name="aicarmine_local_subagent_run_readonly",
        description="Run one bounded Ollama 11434 local subagent task with an explicit read-only tool surface.",
        input_schema=object_schema(
            {
                "task": string_prop(),
                "initial_context": string_prop(),
                "endpoint": string_prop(DEFAULT_ENDPOINT),
                "model": string_prop(DEFAULT_MODEL),
                "allowed_tools": string_array_prop(),
                "max_tool_rounds": integer_prop(4, 0, 8),
                "timeout_seconds": integer_prop(120, 5, 600),
                "num_ctx": integer_prop(262144, 2048, 262144),
                "temperature": number_prop(0.1, 0.0, 2.0),
                "include_tool_transcript": boolean_prop(True),
            },
            required=["task"],
        ),
        handler=_run_readonly,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(server_name=SERVER_NAME, server_version=SERVER_VERSION, tools=tools, health_tool="aicarmine_local_subagent_health", real_tool="aicarmine_local_subagent_capabilities", real_args={})
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
