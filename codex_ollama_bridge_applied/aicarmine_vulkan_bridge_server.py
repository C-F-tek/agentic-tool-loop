from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field


AGENT_URL = os.environ.get("AICARMINE_VULKAN_AGENT_URL", "http://127.0.0.1:3572/vulkan/agent")
BRIDGE_TIMEOUT_SECONDS = int(os.environ.get("AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS", "360"))
DEFAULT_INTERNAL_TOOLS = [
    "repo_capabilities",
    "repo_status",
    "repo_search",
    "repo_read",
    "repo_command",
    "vulkan_helper",
]
PUBLIC_TOOL_ALIASES = [
    "helper_for_all",
    "help_for_all",
    "repo_capabilities",
    "repo_status",
    "repo_search",
    "repo_read",
    "repo_command",
    "vulkan_helper",
]


app = FastAPI(
    title="AI-Carmine helper_for_all Native Bridge",
    version="2.0.0",
    description=(
        "OpenWebUI-facing native helper_for_all tool for the primary 30B. "
        "The 30B must call this tool for local repo work, multi-step helper tasks, file/code analysis, "
        "finding problems, applying user-approved plans, validation, safe commands, logs, artifacts, "
        "or any request that needs local evidence. The tool already knows the configured local repository; "
        "the 30B should not ask the user for language or repo path before calling it."
    ),
)


class HelperForAllRequest(BaseModel):
    """Permissive public request shape for OpenWebUI native tool calling."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    request: str = Field(
        "",
        description=(
            "Specific local task. For first triage you may ask to analyze the repo, but follow-up calls must be "
            "specific: name the target file, exact search query, validation command, or patch intent. Use this for "
            "repo analysis, finding problems, file search/read, git status, diff-check, compileall, validation, "
            "safe run commands, logs, artifacts, multi-step helper work, and applying user-approved plans. "
            "The local repo is already known."
        ),
    )
    function: str = Field(
        "",
        description=(
            "Optional internal hint: repo_capabilities, repo_status, repo_tree, repo_search, "
            "repo_read, repo_apply_patch, repo_write_file, repo_validate, repo_command, or vulkan_helper."
        ),
    )
    action: str = Field(
        "",
        description=(
            "Job action only: start, status, result or cancel. "
            "For any new repo/code/file task, use start or omit action. "
            "Do not use old function-style actions such as search_text, read_file or validate."
        ),
    )
    job_id: str = Field("", description="Optional agent job id for action=status/result/cancel.")
    max_steps: int = Field(20, ge=1, le=60, description="Maximum background agent steps for action=start.")
    approval_mode: str = Field("safe_write_lab", description="Agent approval policy, for example safe_write_lab or read_only.")
    return_mode: str = Field(
        "wait",
        description=(
            "Default wait: action=start keeps the tool call open until the backend job reaches "
            "completed/blocked/failed/max_steps/cancelled or wait_seconds expires. "
            "Use background only for explicit fire-and-forget."
        ),
    )
    wait_seconds: int = Field(
        900,
        ge=1,
        le=1800,
        description="Maximum seconds 3571/3572 should wait for a terminal job result when return_mode=wait.",
    )
    path: str = Field("", description="Repo-relative file path for specific file reads.")
    paths: list[str] = Field(default_factory=list, description="Repo-relative file paths for specific reads.")
    query: str = Field("", description="Exact search query for repo_search-style context acquisition.")
    command: str = Field("", description="Safe command or validation command for repo_command when explicitly needed.")
    user_consent: str = Field("", description="Required confirmation text for dangerous commands; normally empty.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Optional structured parameters for the hinted function.")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Optional alternate structured parameters.")
    context: str = Field("", description="Optional short context from the 30B.")
    expected_output: str = Field("", description="Optional requested result shape.")
    mode: str = Field("tool_helper", description="Optional mode hint.")
    timeout_seconds: int = Field(240, ge=15, le=900, description="Maximum wait for Vulkan/tool result.")


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        data = dict(payload)
    elif hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    else:
        data = {"value": payload}

    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)) and not value:
            continue
        cleaned[str(key)] = value
    return cleaned


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _timeout_from(payload: dict[str, Any]) -> int:
    default_timeout = int(os.environ.get("AICARMINE_VULKAN_DEFAULT_TIMEOUT_SECONDS", "1200"))

    try:
        timeout = int(payload.get("timeout_seconds") or payload.get("timeout") or default_timeout)
    except Exception:
        timeout = default_timeout

    try:
        wait_seconds = int(payload.get("wait_seconds") or 0)
    except Exception:
        wait_seconds = 0

    if wait_seconds > 0:
        timeout = max(timeout, wait_seconds + 60)

    return min(max(timeout, 15), BRIDGE_TIMEOUT_SECONDS)
def _build_agent_payload(raw_payload: dict[str, Any], public_tool_x: str = "helper_for_all") -> dict[str, Any]:
    requested_function = _first_text(
        raw_payload,
        "function",
        "tool_name",
        "tool",
        "name",
        "operation",
        "operationId",
        "action",
        "command_name",
    )
    request_text = _first_text(
        raw_payload,
        "request",
        "task",
        "query",
        "prompt",
        "instruction",
        "command",
        "pattern",
        "path",
        "context",
    )
    if not request_text:
        request_text = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)[:12000]

    parameters = _first_dict(raw_payload, "parameters", "arguments", "args", "input", "payload")
    timeout_seconds = _timeout_from(raw_payload)

    return {
        "request": request_text,
        "task": request_text,
        "context": raw_payload.get("context", "") if isinstance(raw_payload.get("context"), str) else "",
        "expected_output": raw_payload.get("expected_output", "") if isinstance(raw_payload.get("expected_output"), str) else "",
        "mode": raw_payload.get("mode", "tool_helper") if isinstance(raw_payload.get("mode"), str) else "tool_helper",
        "tool_name": public_tool_x,
        "bridge_public_tool_x": public_tool_x,
        "requested_function": requested_function,
        "requested_tool_name": requested_function,
        "arguments": raw_payload,
        "parameters": parameters,
        "requested_parameters": parameters,
        "available_tools": (
            raw_payload.get("available_tools")
            if isinstance(raw_payload.get("available_tools"), list)
            else DEFAULT_INTERNAL_TOOLS
        ),
        "timeout_seconds": timeout_seconds,
        "raw_bridge_payload": raw_payload,
        "bridge_forwarding_mode": "native_multi_tool_alias_to_3572_vulkan_always",
        "wrapper_expected_contract": {
            "type": "deterministic_public_tool_result",
            "public_tool_x": public_tool_x,
            "owner": "3572 broker",
            "required_top_level_keys": [
                "ok",
                "tool_name",
                "tool_result_for",
                "called_by_30b",
                "arguments_from_30b",
                "result",
                "summary_for_30b",
            ],
        },
        "bridge_contract": (
            f"30B/OpenWebUI -> 3571 public tool {public_tool_x} -> 3572 broker -> "
            "11435/Vulkan always selects internal tool L -> 3572 dispatcher executes L -> "
            f"3572 deterministic wrapper maps L result as public tool {public_tool_x}."
        ),
        "bridge_note": (
            f"3571 does not execute local tools and does not answer. It forwards public tool {public_tool_x} "
            "to 3572/Vulkan and returns the completed deterministic tool result."
        ),
    }


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    started = time.time()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "service": "vulkan_bridge",
            "bridge_status": "AGENT_HTTP_ERROR",
            "agent_url": url,
            "http_status": exc.code,
            "elapsed_seconds": round(time.time() - started, 3),
            "message_for_30b": "3571 reached 3572, but 3572 returned an HTTP error.",
            "agent_error_body": raw[:12000],
        }
    except Exception as exc:
        error_text = str(exc)
        is_timeout = "timed out" in error_text.lower() or type(exc).__name__ in {"TimeoutError", "URLError"}
        return {
            "ok": False,
            "service": "vulkan_bridge",
            "bridge_status": "AGENT_TIMEOUT" if is_timeout else "AGENT_UNREACHABLE",
            "agent_url": url,
            "error_type": "BackendTimeout" if is_timeout else type(exc).__name__,
            "error": error_text,
            "elapsed_seconds": round(time.time() - started, 3),
            "message_for_30b": "3571 forwarded the public repo/helper tool, but no valid 3572 result was received.",
        }

    try:
        decoded = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        return {
            "ok": False,
            "service": "vulkan_bridge",
            "bridge_status": "AGENT_INVALID_JSON",
            "agent_url": url,
            "http_status": status,
            "elapsed_seconds": round(time.time() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "raw": raw[:12000],
            "message_for_30b": "3572 responded, but not with valid JSON.",
        }

    if not isinstance(decoded, dict):
        decoded = {"ok": True, "agent_result": decoded}

    decoded.setdefault("ok", True)
    decoded["bridge_status"] = "AGENT_RESULT_RETURNED"
    decoded["bridge_waited_for_agent"] = True
    decoded["bridge_elapsed_seconds"] = round(time.time() - started, 3)
    decoded["bridge_agent_url"] = url
    decoded["bridge_contract"] = payload["bridge_contract"]
    expected_tool = str(payload.get("bridge_public_tool_x") or "helper_for_all")
    if decoded.get("tool_result_for") != expected_tool or decoded.get("called_by_30b") != expected_tool:
        decoded["bridge_wrapper_guard"] = {
            "expected_public_tool_x": expected_tool,
            "received_tool_name": decoded.get("tool_name"),
            "received_tool_result_for": decoded.get("tool_result_for"),
            "received_called_by_30b": decoded.get("called_by_30b"),
            "action": "normalized_public_tool_metadata_only",
        }
    decoded["tool_name"] = expected_tool
    decoded["tool_result_for"] = expected_tool
    decoded["called_by_30b"] = expected_tool
    decoded.setdefault("operation_id", expected_tool)
    decoded.setdefault("wrapper_expected_contract", payload.get("wrapper_expected_contract"))
    decoded.setdefault(
        "message_for_30b",
        "The public repo/helper tool returned a local evidence-bound result. Use the result fields directly; do not invent missing evidence.",
    )
    return decoded

def _looks_like_truncated_refactor_request(raw_payload: dict[str, Any]) -> bool:
    action = _first_text(raw_payload, "action", "job_action").lower()
    if action not in {"", "start", "run", "execute"}:
        return False

    request = _first_text(raw_payload, "request", "task", "query", "prompt", "instruction").lower()
    function = _first_text(raw_payload, "function", "tool_name", "operation_id").lower()

    if not request:
        return True

    generic_refactor = (
        "identifica un'area concreta di refactoring" in request
        or "identify a concrete refactoring area" in request
        or "analyze the repository" in request
        or "analizza lo stato della repository" in request
    )

    has_write_intent = any(
        token in request
        for token in (
            "applica",
            "applicare",
            "patch",
            "modifica",
            "write",
            "apply",
            "refactor and apply",
            "apply a patch",
        )
    )

    # Se il modello dichiara una function interna ma la request è generica,
    # sta probabilmente riassumendo invece di passare la richiesta utente completa.
    internal_function_hint = function in {
        "repo_status",
        "repo_search",
        "repo_read",
        "repo_tree",
        "repo_validate",
    }

    return generic_refactor and internal_function_hint and not has_write_intent
def _handle_helper(req: HelperForAllRequest, alias_called: str) -> dict[str, Any]:
    raw_payload = _payload_to_dict(req)
    public_tool_x = alias_called if alias_called in PUBLIC_TOOL_ALIASES else "helper_for_all"
    if public_tool_x == "vulkan_helper" and _looks_like_truncated_refactor_request(raw_payload):
        return {
            "ok": True,
            "service": "vulkan_bridge",
            "bridge_status": "BLOCKED_TRUNCATED_USER_REQUEST",
            "tool_name": public_tool_x,
            "tool_result_for": public_tool_x,
            "called_by_30b": public_tool_x,
            "operation_id": public_tool_x,
            "bridge_public_tool": public_tool_x,
            "bridge_alias_called": alias_called,
            "bridge_received_payload_shape": sorted(raw_payload.keys()),
            "bridge_forwarded_to_vulkan": False,
            "bridge_forwarding_mode": "blocked_before_3572_truncated_request",
            "message_for_30b": (
                "La tool-call è stata bloccata perché la richiesta sembra una sintesi incompleta. "
                "Devi reinviare vulkan_helper con action=start e request contenente la richiesta utente completa, "
                "incluse parole come applica/apply/patch/modifica se presenti nel messaggio originale. "
                "Non trasformare una richiesta di patch in una semplice analisi repo_status."
            ),
            "requires_full_user_request": True,
        }
    if public_tool_x not in {"helper_for_all", "help_for_all"}:
        raw_payload.setdefault("function", public_tool_x)
        raw_payload.setdefault("tool_name", public_tool_x)
        raw_payload.setdefault("operation_id", public_tool_x)
    
    agent_payload = _build_agent_payload(raw_payload, public_tool_x=public_tool_x)
    timeout = int(agent_payload["timeout_seconds"])
    result = _post_json(AGENT_URL, agent_payload, timeout=timeout)
    result.setdefault("service", "vulkan_bridge")
    result["bridge_public_tool"] = public_tool_x
    result["bridge_alias_called"] = alias_called
    result["bridge_received_payload_shape"] = sorted(raw_payload.keys())
    result["bridge_forwarded_to_vulkan"] = True
    result["bridge_forwarding_mode"] = "native_multi_tool_alias_to_3572"
    return result


@app.get("/health", include_in_schema=False)
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "aicarmine-helper-for-all-bridge",
        "agent_url": AGENT_URL,
        "timeout_seconds": BRIDGE_TIMEOUT_SECONDS,
        "public_tools": PUBLIC_TOOL_ALIASES,
        "contract": "OpenWebUI registers explicit repo tools plus helper_for_all; 3571 forwards to 3572/Vulkan.",
    }


@app.post(
    "/helper_for_all",
    operation_id="helper_for_all",
    summary="Native universal local helper for repo and multi-task work",
    description=(
        "CALL THIS TOOL whenever the user asks to analyze the local repo, find real problems, inspect files/code, "
        "search/read the repository, check git status/diff, validate, run safe commands, use a helper, execute a "
        "multi-step local task, or apply a user-approved plan to the repo. Do not ask the user what language or "
        "repository path to use: this tool already knows the configured local repo. Do not use OpenWebUI knowledge "
        "or notes for local repo evidence. Send the user's request in `request`. After the first triage, avoid "
        "generic repeat requests: call this same tool with a specific `function` hint and `path`, `query`, or "
        "`command` from the previous result's `useful_next_calls`."
    ),
)
def helper_for_all(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="helper_for_all")


@app.post(
    "/repo_capabilities",
    operation_id="repo_capabilities",
    summary="List local repo tool capabilities and routing policy",
    description=(
        "CALL THIS TOOL when you are unsure which repo/file/tool action to use. "
        "It returns the available local actions, required arguments, safety policy, and next-call examples."
    ),
)
def repo_capabilities(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="repo_capabilities")


@app.post(
    "/repo_status",
    operation_id="repo_status",
    summary="Read git status, diff check, changed files and stack",
    description="Use for branch/status/diff/preflight questions. Read-only.",
)
def repo_status_public(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="repo_status")


@app.post(
    "/repo_search",
    operation_id="repo_search",
    summary="Search repository code and documentation",
    description="Use when the user asks to find symbols, errors, TODOs, paths, functions, files or text matches.",
)
def repo_search_public(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="repo_search")


@app.post(
    "/repo_read",
    operation_id="repo_read",
    summary="Read one or more repo-relative files",
    description="Use when a specific file path or file list is known. Pass path or paths.",
)
def repo_read_public(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="repo_read")


@app.post(
    "/repo_command",
    operation_id="repo_command",
    summary="Run a safe diagnostic repository command",
    description="Use only for safe validation/smoke/compile/status commands. Dangerous commands require user_consent.",
)
def repo_command_public(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="repo_command")


@app.post(
    "/vulkan_helper",
    operation_id="vulkan_helper",
    summary="Single public Codex-like local workspace agent",
    description=(
        "CALL THIS SINGLE PUBLIC TOOL for every local repository, file, code, git, search, read, "
        "validation, smoke, diagnostic, patch-planning, safe-editing or artifact task. "
        "For a new task, send the full user request once with action=start or omit action. "
        "Do not call function-style actions such as repo_status/search_text/read_file. "
        "The backend will create a background agent job, return job_id and job_url, then run the controlled "
        "planner loop outside the chat. For an existing job, call action=status or action=result with job_id. "
        "3572 owns the job workspace, HTTP dashboard, events, artifacts and internal deterministic tools."
    ),
)
def vulkan_helper_public(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="vulkan_helper")

@app.post(
    "/help_for_all",
    operation_id="help_for_all",
    summary="Alias for helper_for_all",
    description=(
        "Alias for prompts that say HELP_FOR_ALL. Same native local helper capability as helper_for_all."
    ),
)
def help_for_all(req: HelperForAllRequest) -> dict[str, Any]:
    return _handle_helper(req, alias_called="help_for_all")


def _native_helper_openapi() -> dict[str, Any]:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    allowed = {f"/{name}" for name in PUBLIC_TOOL_ALIASES}
    schema["paths"] = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path in allowed
    }
    schema["x-aicarmine-tool-surface"] = "native_multi_tool_aliases_to_single_3572_broker"
    schema["x-aicarmine-contract"] = (
        "OpenAPI exposes explicit repo/file helper tools plus helper_for_all fallback to the 30B. "
        "3571 forwards every public tool call to 3572; 11435/Vulkan always selects/adapts internal tool L; "
        "3572 executes L and deterministically maps the dispatcher result into the original public tool result."
    )
    schema["x-aicarmine-register_this_in_openwebui"] = "http://127.0.0.1:3571/openapi.json"
    schema["x-aicarmine-internal_agent"] = AGENT_URL
    return schema


app.openapi_schema = None
app.openapi = _native_helper_openapi
