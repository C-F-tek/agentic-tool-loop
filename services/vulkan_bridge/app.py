from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from .config import BridgeConfig, int_env, bool_env, load_bridge_config_from_env
from .application.request_payload import (
    first_dict,
    first_text,
    payload_to_dict,
    public_agent_arguments,
)
from .application.response_values import (
    bridge_result_digest,
    compact_text,
    json_size,
)
from .application.public_field_names import normalize_public_payload_field_names
from .application.public_payload_linter import lint_public_payload
from .openapi_builder import build_native_helper_openapi

OPENWEBUI_PUBLIC_TOOLS = (
    "helper_for_all",
    "help_for_all",
    "repo_capabilities",
    "repo_status",
    "repo_search",
    "repo_read",
    "repo_command",
    "vulkan_helper",
)
PLANNER_INTERNAL_TOOLS = (
    "repo_capabilities",
    "repo_status",
    "repo_tree",
    "repo_search",
    "repo_read",
    "repo_list_files",
    "repo_apply_patch",
    "repo_write_file",
    "repo_validate",
    "repo_command",
    "terminal_run_command_wait",
    "terminal_search_files",
    "terminal_list_files",
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
    "runtime_sqlite_memory_cleanup",
    "vulkan_helper",
)


def _broker_capability_map() -> dict[str, Any]:
    try:
        from aicarmine_broker.tool_registry import capability_map  # noqa: PLC0415
    except BaseException:  # pragma: no cover - keeps 3571 importable during partial deploys
        return {}
    return capability_map()


BRIDGE_CONFIG: BridgeConfig = load_bridge_config_from_env()


def _int_env(name: str, default: int) -> int:
    return int_env(name, default)


def _bool_env(name: str, default: bool) -> bool:
    return bool_env(name, default)


AGENT_URL = BRIDGE_CONFIG.agent_url
BRIDGE_TIMEOUT_SECONDS = BRIDGE_CONFIG.bridge_timeout_seconds
BRIDGE_MAX_OPENWEBUI_RESPONSE_CHARS = BRIDGE_CONFIG.max_openwebui_response_chars
BRIDGE_MAX_OPENWEBUI_SUMMARY_CHARS = BRIDGE_CONFIG.max_openwebui_summary_chars
BRIDGE_MAX_OPENWEBUI_ANSWER_CHARS = BRIDGE_CONFIG.max_openwebui_answer_chars
BRIDGE_OPENWEBUI_INLINE_FILE_CHARS = BRIDGE_CONFIG.openwebui_inline_file_chars
BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS = BRIDGE_CONFIG.openwebui_inline_evidence_chars
OPENWEBUI_FINAL_TOOL_SETTLE_SECONDS = BRIDGE_CONFIG.final_tool_settle_seconds
OPENWEBUI_FINAL_UNLOAD_PLANNER = BRIDGE_CONFIG.final_unload_planner
OPENWEBUI_FINAL_UNLOAD_TIMEOUT_SECONDS = BRIDGE_CONFIG.final_unload_timeout_seconds
PLANNER_URL = BRIDGE_CONFIG.planner_url
PLANNER_MODEL = BRIDGE_CONFIG.planner_model
DEFAULT_INTERNAL_TOOLS = list(PLANNER_INTERNAL_TOOLS)
PUBLIC_TOOL_ALIASES = list(OPENWEBUI_PUBLIC_TOOLS)
OPENWEBUI_VISIBLE_TOOL_ALIASES = ("vulkan_helper",)


app = FastAPI(
    title="AI-Carmine vulkan_helper Native Bridge",
    version="2.0.0",
    description=(
        "OpenWebUI-facing native vulkan_helper tool. "
        "Use one call for a local repo task; the default wait response returns the completed planner "
        "inline evidence. Completed responses put payload_index near the top: "
        "it tells the model which fields contain concrete results such as diffs/file content and "
        "which fields are only descriptions, review metadata or navigation hints. After a terminal "
        "result, answer from payload_index, priority_evidence and tool_context instead of issuing "
        "follow-up tool calls."
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
            "The local repo is already known. Windows/Open Terminal note: for user filesystem work, the backend has terminal_list_files, terminal_search_files and terminal_run_command_wait adapters that normalize C:\\Users paths, force PowerShell non-interactive execution, poll to final output and strip ANSI noise."
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
    mode: str = Field("tool_helper", description="Optional mode hint.")
    timeout_seconds: int = Field(240, ge=15, le=900, description="Maximum wait for Vulkan/tool result.")


class VulkanHelperRequest(BaseModel):
    """OpenWebUI-visible request shape for the single public tool."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    request: str = Field(
        "",
        description=(
            "User task for the local agentic loop. Send the full user request once; the helper "
            "runs the controlled backend loop and returns the completed answer plus inline evidence."
        ),
    )


def _public_agent_arguments(raw_payload: dict[str, Any]) -> dict[str, Any]:
    return public_agent_arguments(raw_payload)


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    return payload_to_dict(payload)


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    return first_text(payload, *keys)


def _first_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    return first_dict(payload, *keys)


def _compact_text(value: Any, limit: int) -> str:
    return compact_text(value, limit)


def _json_size(value: Any) -> int:
    return json_size(value)


def _bridge_result_digest(result: Any) -> dict[str, Any]:
    return bridge_result_digest(result)


def _public_payload_lint_mode() -> str:
    return str(os.environ.get("AICARMINE_PUBLIC_PAYLOAD_LINT_MODE", "warn") or "warn")


def _attach_public_payload_lint(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    payload = normalize_public_payload_field_names(payload)
    payload["public_payload_lint"] = lint_public_payload(
        payload,
        mode=_public_payload_lint_mode(),
    )
    return payload



# --- agentic-loop-v2 OpenWebUI context compaction ---
def _agentic_v2_strip_large_for_openwebui(value, depth=0):
    if depth > 6:
        return {"omitted": "max_depth"}
    if isinstance(value, str):
        return _compact_text(value, 1200)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        limit = 30 if depth <= 2 else 12
        out = [_agentic_v2_strip_large_for_openwebui(v, depth + 1) for v in value[:limit]]
        if len(value) > limit:
            out.append({"omitted_items": len(value) - limit})
        return out
    if isinstance(value, dict):
        large_keys = {
            "content", "content_preview", "text", "raw", "raw_text",
            "raw_planner_text", "raw_planner_text_preview", "full_raw",
            "full_result", "items", "files_preview",
        }
        out = {}
        for k, v in value.items():
            if k in large_keys:
                if isinstance(v, str):
                    out[k + "_omitted_chars"] = len(v)
                elif isinstance(v, list):
                    out[k + "_omitted_items"] = len(v)
                else:
                    out[k + "_omitted"] = True
                continue
            out[k] = _agentic_v2_strip_large_for_openwebui(v, depth + 1)
        return out
    return _compact_text(str(value), 500)


def _legacy_agentic_v2_compact_context_for_openwebui(ctx):
    if not isinstance(ctx, dict):
        return ctx
    keep = {}
    for key in (
        "type", "contract_type", "not_a_summary", "openwebui_usage", "job",
        "contract", "execution_contract", "final_answer",
        "next_action_for_30b", "evidence_contract_at_terminal",
        "evidence_contract_at_finish", "blocked_by", "artifacts", "result_digest",
    ):
        if ctx.get(key) not in (None, "", [], {}):
            keep[key] = _agentic_v2_strip_large_for_openwebui(ctx.get(key))

    planner = ctx.get("planner")
    if isinstance(planner, dict):
        keep["planner"] = {
            "planner_model": planner.get("planner_model"),
            "decisions": _agentic_v2_strip_large_for_openwebui((planner.get("decisions") or [])[-16:]),
            "validation_rejections": _agentic_v2_strip_large_for_openwebui((planner.get("validation_rejections") or [])[-10:]),
        }

    executed = ctx.get("executed_tools")
    if isinstance(executed, list):
        keep["executed_tools"] = _agentic_v2_strip_large_for_openwebui(executed[-24:])

    history = ctx.get("history")
    if isinstance(history, list):
        keep["history_digest"] = _agentic_v2_strip_large_for_openwebui(history[-12:])
        keep["history_omitted_full_items"] = max(0, len(history) - 12)

    keep.setdefault("openwebui_usage", {})
    if isinstance(keep["openwebui_usage"], dict):
        keep["openwebui_usage"]["rule"] = (
            "Read the top-level evidence_guide_for_30b first. Use evidence_contract_at_terminal, "
            "planner.validation_rejections, executed_tools and artifacts for diagnosis. "
            "Do not ask the user to invent a new plan when next_action_for_30b is present."
        )
    return keep

def _legacy_compact_for_openwebui(decoded: dict[str, Any]) -> dict[str, Any]:
    if _json_size(decoded) <= BRIDGE_MAX_OPENWEBUI_RESPONSE_CHARS:
        return decoded

    compacted: dict[str, Any] = {}
    keep_keys = (
        "ok", "service", "mode", "required_top_level_keys", "payload_index_for_30b",
        "priority_evidence_for_30b", "openwebui_usage", "tool_context_for_30b",
        "result",
    )
    for key in keep_keys:
        if decoded.get(key) not in (None, "", [], {}):
            compacted[key] = decoded.get(key)

    compacted.setdefault("required_top_level_keys", [
        "ok",
        "service",
        "mode",
        "required_top_level_keys",
        "payload_index_for_30b",
        "priority_evidence_for_30b",
        "openwebui_usage",
        "tool_context_for_30b",
    ])
    compacted.setdefault("openwebui_usage", {
        "primary_payload_fields": [
            "payload_index_for_30b",
            "priority_evidence_for_30b",
            "tool_context_for_30b",
            "result",
        ],
        "rule": "Leggi i payload primari inline; non usare campi narrativi o path locali come sostituti.",
    })
    compacted["bridge_compacted_for_openwebui"] = True
    compacted["bridge_original_response_chars"] = _json_size(decoded)
    compacted["bridge_compaction_rule"] = (
        "Large nested agent payload retained only through primary inline fields; no narrative/path substitute promoted."
    )
    return compacted


def _effective_wait_seconds(payload: dict[str, Any]) -> int:
    action = str(payload.get("action") or "").strip().lower()
    if action in {"status", "result", "cancel"}:
        return 0
    return_mode = str(payload.get("return_mode") or "wait").strip().lower()
    try:
        raw_wait = int(payload.get("wait_seconds") or os.environ.get("AICARMINE_AGENT_RETURN_WAIT_SECONDS") or 900)
    except BaseException:
        return 900
    if return_mode in {"background", "async", "fire_and_forget"}:
        return int(os.environ.get("AICARMINE_AGENT_RETURN_WAIT_SECONDS") or 900)
    return raw_wait


def _final_handoff_timeout_budget_seconds() -> int:
    unload_budget = OPENWEBUI_FINAL_UNLOAD_TIMEOUT_SECONDS if OPENWEBUI_FINAL_UNLOAD_PLANNER else 0
    return unload_budget + OPENWEBUI_FINAL_TOOL_SETTLE_SECONDS


def _required_bridge_timeout_seconds(payload: dict[str, Any]) -> int:
    wait_seconds = _effective_wait_seconds(payload)
    if wait_seconds <= 0:
        return 15
    return wait_seconds + _final_handoff_timeout_budget_seconds() + 60


def _timeout_from(payload: dict[str, Any]) -> int:
    default_timeout = _int_env("AICARMINE_VULKAN_DEFAULT_TIMEOUT_SECONDS", BRIDGE_TIMEOUT_SECONDS)

    try:
        timeout = int(payload.get("timeout_seconds") or payload.get("timeout") or default_timeout)
    except BaseException:
        timeout = default_timeout

    timeout = max(timeout, _required_bridge_timeout_seconds(payload))

    return min(max(timeout, 15), BRIDGE_TIMEOUT_SECONDS)


def _semantic_request_from_tool_envelope(raw_payload: dict[str, Any], requested_function: str, public_tool_x: str) -> str:
    """Surface missing user request instead of inventing a semantic fallback.

    A public tool envelope such as {"function":"repo_tree"} is transport
    metadata, not the user's task.  Do not rewrite it into "analyze repository";
    that hides the upstream OpenWebUI/tool-call bug and lets the planner produce
    a fake one-step final.  Return an explicit input-error goal that 3572 blocks
    and exposes in the terminal result.
    """
    function = str(requested_function or raw_payload.get("function") or raw_payload.get("tool_name") or public_tool_x or "").strip()
    return (
        "__AICARMINE_INPUT_ERROR_MISSING_USER_REQUEST__ "
        "The public helper call did not include request/task/query/prompt/instruction. "
        f"public_tool={public_tool_x}; requested_function={function or '<none>'}; "
        f"raw_arguments={json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)[:3000]}"
    )


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
        request_text = _semantic_request_from_tool_envelope(raw_payload, requested_function, public_tool_x)

    forwarded_arguments = _public_agent_arguments(raw_payload)
    wait_seconds = _effective_wait_seconds(raw_payload)
    forwarded_arguments = dict(forwarded_arguments or {})
    forwarded_arguments["return_mode"] = "wait"
    forwarded_arguments["wait_seconds"] = wait_seconds
    parameters = _first_dict(forwarded_arguments, "parameters", "arguments", "args", "input", "payload")
    required_timeout_seconds = _required_bridge_timeout_seconds(raw_payload)
    timeout_seconds = _timeout_from(raw_payload)

    return {
        "request": request_text,
        "task": request_text,
        "context": raw_payload.get("context", "") if isinstance(raw_payload.get("context"), str) else "",
        "mode": raw_payload.get("mode", "tool_helper") if isinstance(raw_payload.get("mode"), str) else "tool_helper",
        "tool_name": public_tool_x,
        "bridge_public_tool_x": public_tool_x,
        "requested_function": requested_function,
        "requested_tool_name": requested_function,
        "arguments": forwarded_arguments,
        "parameters": parameters,
        "requested_parameters": parameters,
        "return_mode": "wait",
        "wait_seconds": wait_seconds,
        "available_tools": (
            raw_payload.get("available_tools")
            if isinstance(raw_payload.get("available_tools"), list)
            else DEFAULT_INTERNAL_TOOLS
        ),
        "timeout_seconds": timeout_seconds,
        "bridge_timeout_required_seconds": required_timeout_seconds,
        "bridge_timeout_capacity_seconds": BRIDGE_TIMEOUT_SECONDS,
        "bridge_timeout_configuration_ok": timeout_seconds >= required_timeout_seconds,
        "raw_bridge_payload": forwarded_arguments,
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
                "evidence_guide_for_30b",
                "tool_context_for_30b",
            ],
        },
        "bridge_contract": (
            f"30B/OpenWebUI -> 3571 public tool {public_tool_x} -> 3572 broker -> "
            "3572 starts the planner loop; Vulkan/11435 is a repair/helper lane only when needed -> "
            f"3572 deterministic wrapper maps L result as public tool {public_tool_x}."
        ),
        "bridge_note": (
            f"3571 does not execute local tools and does not answer. It forwards public tool {public_tool_x} "
            "to 3572/Vulkan and returns the completed deterministic tool result."
        ),
    }


def _is_terminal_agent_result(decoded: dict[str, Any]) -> bool:
    if not isinstance(decoded, dict):
        return False
    status = str(decoded.get("status") or "").strip().lower()
    if status in {"completed", "blocked_needs_attention", "failed", "max_steps", "cancelled"}:
        return True
    if decoded.get("wait_completed") is True and decoded.get("job_id"):
        return True
    if isinstance(decoded.get("job_ok"), bool) and decoded.get("job_id"):
        return True
    return False


def _ollama_base_url_from_chat_url(url: str) -> str:
    raw = str(url or "").strip().rstrip("/")
    for suffix in ("/api/chat", "/api/generate"):
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    if "/api/" in raw:
        return raw.split("/api/", 1)[0].rstrip("/")
    return raw


def _unload_planner_model_for_openwebui() -> dict[str, Any]:
    started = time.time()
    if not OPENWEBUI_FINAL_UNLOAD_PLANNER:
        return {"attempted": False, "reason": "disabled"}
    model = str(PLANNER_MODEL or "").strip()
    if not model:
        return {"attempted": False, "reason": "missing_planner_model"}
    base_url = _ollama_base_url_from_chat_url(PLANNER_URL)
    endpoint = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": "",
        "stream": False,
        "keep_alive": 0,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OPENWEBUI_FINAL_UNLOAD_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
        return {
            "attempted": True,
            "ok": 200 <= int(status) < 300,
            "http_status": status,
            "planner_model": model,
            "planner_url": PLANNER_URL,
            "unload_endpoint": endpoint,
            "elapsed_seconds": round(time.time() - started, 3),
            "raw_preview": raw[:1000],
        }
    except BaseException as exc:
        return {
            "attempted": True,
            "ok": False,
            "planner_model": model,
            "planner_url": PLANNER_URL,
            "unload_endpoint": endpoint,
            "elapsed_seconds": round(time.time() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }


def _apply_openwebui_final_handoff(decoded: dict[str, Any]) -> None:
    if not _is_terminal_agent_result(decoded):
        decoded.setdefault("openwebui_final_tool_settle_applied", False)
        decoded.setdefault("openwebui_final_tool_settle_seconds", 0)
        return
    unload_result = _unload_planner_model_for_openwebui()
    settle_seconds = OPENWEBUI_FINAL_TOOL_SETTLE_SECONDS
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    decoded["openwebui_final_unload_planner"] = unload_result
    decoded["openwebui_final_tool_settle_applied"] = settle_seconds > 0
    decoded["openwebui_final_tool_settle_seconds"] = settle_seconds
    decoded["openwebui_final_handoff"] = {
        "terminal_result": True,
        "planner_unload_attempted": bool(unload_result.get("attempted")),
        "planner_unload_ok": unload_result.get("ok") if unload_result.get("attempted") else None,
        "settle_seconds": settle_seconds,
        "reason": "free_planner_vram_before_returning_vulkan_helper_result_to_openwebui",
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
            "evidence_guide_for_30b": "3571 reached 3572, but 3572 returned an HTTP error.",
            "tool_context_for_30b": {
                "type": "bridge_error_context",
                "top_level_evidence_guide_field": "evidence_guide_for_30b",
                "bridge_status": "AGENT_HTTP_ERROR",
            },
            "agent_error_body": raw[:12000],
        }
    except BaseException as exc:
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
            "evidence_guide_for_30b": "3571 forwarded the public repo/helper tool, but no valid 3572 result was received.",
            "tool_context_for_30b": {
                "type": "bridge_error_context",
                "top_level_evidence_guide_field": "evidence_guide_for_30b",
                "bridge_status": "AGENT_TIMEOUT" if is_timeout else "AGENT_UNREACHABLE",
            },
        }

    try:
        decoded = json.loads(raw) if raw.strip() else {}
    except BaseException as exc:
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
            "evidence_guide_for_30b": "3572 responded, but not with valid JSON.",
            "tool_context_for_30b": {
                "type": "bridge_error_context",
                "top_level_evidence_guide_field": "evidence_guide_for_30b",
                "bridge_status": "AGENT_INVALID_JSON",
            },
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
    called_by_value = decoded.get("called_by") or decoded.get("called_by_30b")
    if decoded.get("tool_result_for") != expected_tool or called_by_value != expected_tool:
        decoded["bridge_wrapper_guard"] = {
            "expected_public_tool_x": expected_tool,
            "received_tool_name": decoded.get("tool_name"),
            "received_tool_result_for": decoded.get("tool_result_for"),
            "received_called_by": called_by_value,
            "action": "normalized_public_tool_metadata_only",
        }
    decoded["tool_name"] = expected_tool
    decoded["tool_result_for"] = expected_tool
    decoded.pop("called_by_30b", None)
    decoded["called_by"] = expected_tool
    decoded.setdefault("arguments_from", payload.get("raw_bridge_payload") or payload.get("arguments") or {})
    decoded.setdefault("operation_id", expected_tool)
    decoded.setdefault("wrapper_expected_contract", payload.get("wrapper_expected_contract"))
    decoded.setdefault(
        "evidence_guide_for_30b",
        "The public repo/helper tool returned a local evidence-bound result. Use the indexed result fields directly; do not invent missing evidence.",
    )
    _apply_openwebui_final_handoff(decoded)
    return _compact_for_openwebui(decoded)

def _handle_helper(req: HelperForAllRequest, alias_called: str) -> dict[str, Any]:
    raw_payload = _payload_to_dict(req)
    public_tool_x = alias_called if alias_called in PUBLIC_TOOL_ALIASES else "helper_for_all"
    if public_tool_x not in {"helper_for_all", "help_for_all"}:
        raw_payload.setdefault("function", public_tool_x)
        raw_payload.setdefault("tool_name", public_tool_x)
        raw_payload.setdefault("operation_id", public_tool_x)
    
    agent_payload = _build_agent_payload(raw_payload, public_tool_x=public_tool_x)
    if not agent_payload.get("bridge_timeout_configuration_ok", True):
        return {
            "ok": False,
            "service": "vulkan_bridge",
            "bridge_status": "BRIDGE_TIMEOUT_CONFIGURATION_ERROR",
            "evidence_guide_for_30b": (
                "3571 bridge timeout is lower than the required agent wait plus final OpenWebUI handoff budget."
            ),
            "tool_context_for_30b": {
                "type": "bridge_configuration_error_context",
                "top_level_evidence_guide_field": "evidence_guide_for_30b",
                "bridge_status": "BRIDGE_TIMEOUT_CONFIGURATION_ERROR",
            },
            "bridge_timeout_required_seconds": agent_payload.get("bridge_timeout_required_seconds"),
            "bridge_timeout_capacity_seconds": agent_payload.get("bridge_timeout_capacity_seconds"),
            "bridge_public_tool": public_tool_x,
            "bridge_alias_called": alias_called,
            "bridge_received_payload_shape": sorted(raw_payload.keys()),
            "bridge_forwarded_to_vulkan": False,
        }
    timeout = int(agent_payload["timeout_seconds"])
    result = _post_json(AGENT_URL, agent_payload, timeout=timeout)
    result.setdefault("service", "vulkan_bridge")
    if result.get("status") == "completed" or result.get("job_ok") is True:
        return result
    return result


@app.get("/health", include_in_schema=False)
def health() -> dict[str, Any]:
    registry = _broker_capability_map() if _broker_capability_map else {}
    return {
        "ok": True,
        "service": "aicarmine-helper-for-all-bridge",
        "agent_url": AGENT_URL,
        "timeout_seconds": BRIDGE_TIMEOUT_SECONDS,
        "public_tools": list(OPENWEBUI_VISIBLE_TOOL_ALIASES),
        "internal_planner_tools": DEFAULT_INTERNAL_TOOLS,
        "registry": registry,
        "registry_hash": registry.get("registry_hash"),
        "registry_version": registry.get("registry_version"),
        "module_loaded": __name__,
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "python_base_prefix": sys.base_prefix,
        "contract": (
            "3571 receives the OpenWebUI tool call, forwards it to 3572 and waits; "
            "3572 runs the planner loop, wraps the terminal result and returns it to 3571; "
            "3571 then returns ok plus the wrapped result to OpenWebUI."
        ),
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
        "Single OpenWebUI public tool for local repository work. For a new task, send the full "
        "user request once and wait for the completed response. The completed response contains "
        "a top-level payload_index_for_30b before the large evidence blocks. Use that index to "
        "find concrete results: code diffs live in priority_evidence_for_30b.items[*].unified_diff "
        "and tool_context_for_30b.artifacts[*].artifact.unified_diff; file contents live in "
        "priority_evidence_for_30b.items[*].content and tool_context_for_30b.artifacts[*].artifact.content. "
        "content/summary fields are descriptions; validation_commands, manual_review_required and "
        "limits are review/navigation metadata, not reasons to repeat the same call. "
        "Do not call again after a completed result unless the user explicitly asks a new task "
        "or explicitly gives an existing job_id for status/result."
    ),
)
def vulkan_helper_public(req: VulkanHelperRequest) -> dict[str, Any]:
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
    return build_native_helper_openapi(
        app,
        visible_tool_aliases=OPENWEBUI_VISIBLE_TOOL_ALIASES,
        registry_loader=_broker_capability_map if _broker_capability_map else None,
    )


app.openapi_schema = None
app.openapi = _native_helper_openapi


# --- agentic-loop-v9 protocol-observation OpenWebUI tool-result transport ---
# Purpose:
#   Preserve the 3571 -> 3572 -> wait contract, but serialize the post-wait
#   result as a protocol-aware TOOL OBSERVATION for the outer OpenWebUI model.
#
# Rationale:
#   Returning a huge bare dict/JSON makes local Qwen print the JSON. OpenWebUI
#   Native tools pass the method return value as model-visible content, so the
#   return value must explicitly say: this is a tool observation, do not echo,
#   synthesize an answer from the evidence, call the tool again only if needed.

import hashlib as _agentic_v9_hashlib
import json as _agentic_v9_json
import os as _agentic_v9_os
import time as _agentic_v9_time
from pathlib import Path as _agentic_v9_Path


def _agentic_v9_enabled():
    return str(_agentic_v9_os.environ.get("AGENTIC_OPENWEBUI_PROTOCOL_OBSERVATION", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _agentic_v9_preforward_block_allowed():
    return str(_agentic_v9_os.environ.get("AGENTIC_BRIDGE_ALLOW_PREFORWARD_BLOCK", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _agentic_v9_int_env(name, default):
    try:
        return int(str(_agentic_v9_os.environ.get(name, str(default))).strip())
    except BaseException:
        return default


_AGENTIC_V9_OBSERVATION_JSON_CHARS = _agentic_v9_int_env("AGENTIC_OPENWEBUI_OBSERVATION_JSON_CHARS", 90000)
_AGENTIC_V9_ARTIFACT_READ_CHARS = _agentic_v9_int_env("AGENTIC_OPENWEBUI_ARTIFACT_READ_CHARS", 2500000)
_AGENTIC_V9_CONTENT_EXCERPT_CHARS = _agentic_v9_int_env("AGENTIC_OPENWEBUI_CONTENT_EXCERPT_CHARS", 24000)
_AGENTIC_V9_MAX_ITEMS = _agentic_v9_int_env("AGENTIC_OPENWEBUI_MAX_EVIDENCE_ITEMS", 500)


def _agentic_v9_as_dict(value):
    return value if isinstance(value, dict) else {}


def _agentic_v9_as_list(value):
    return value if isinstance(value, list) else []


def _agentic_v9_clip_text(value, limit=None):
    limit = _AGENTIC_V9_CONTENT_EXCERPT_CHARS if limit is None else int(limit)
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 160)] + "\n... <truncated by agentic-loop-v9 observation serializer>"


def _agentic_v9_parse_jsonish(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return _agentic_v9_json.loads(text)
    except BaseException:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return _agentic_v9_json.loads(text[start:end + 1])
        except BaseException:
            return value
    return value


def _agentic_v9_json_dumps(value, *, indent=2):
    return _agentic_v9_json.dumps(value, ensure_ascii=False, indent=indent, default=str)


def _agentic_v9_json_len(value):
    try:
        return len(_agentic_v9_json.dumps(value, ensure_ascii=False, default=str))
    except BaseException:
        return -1


def _agentic_v9_sha256_json(value):
    try:
        raw = _agentic_v9_json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return _agentic_v9_hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    except BaseException:
        return ""


def _agentic_v9_clean(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            c = _agentic_v9_clean(v)
            if c not in (None, "", [], {}):
                out[k] = c
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            c = _agentic_v9_clean(v)
            if c not in (None, "", [], {}):
                out.append(c)
        return out
    return value


_AGENTIC_V9_PUBLIC_POINTER_KEYS = {
    "artifact_path",
    "producer_artifact",
    "final_path",
    "events_path",
    "db",
    "db_path",
    "sqlite_path",
    "document_id",
    "evidence_contract",
    "raw_planner_text_preview",
    "raw_planner_text",
    "raw_text",
    "workspace",
}


def _agentic_v9_public_content_key(key):
    return str(key or "").lower() in {
        "content",
        "content_view",
        "unified_diff",
        "structured_operations",
        "old_text",
        "new_text",
        "stdout",
        "stderr",
        "stdout_tail",
        "stderr_tail",
    }


def _agentic_v9_public_sanitize_text(value, *, content=False):
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?:^|\s+)(?:backup_)?artifact=[A-Za-z]:\\[^\s,}\]]+", " ", text)
    if not content:
        text = re.sub(r"(?:^|\s+)(?:backup_)?artifact=[^\s,}\]]+", " ", text)
        text = re.sub(r'"(?:artifact|artifact_path|producer_artifact|document_id|db|db_path|sqlite_path)"\s*:\s*"[^"]*",?', "", text)
    text = re.sub(r"[A-Za-z]:\\[^\s,}\]]+", "", text)
    text = re.sub(r"https?://(?:127\.0\.0\.1|localhost)[^\s,}\]]*", "", text, flags=re.I)
    text = re.sub(r"\bqwen-agent-workspace[^\s,}\]]*", "", text)
    text = re.sub(r"\bagent-jobs[^\s,}\]]*", "", text)
    text = re.sub(r"\btool-results\\[^\s,}\]]*", "", text)
    text = re.sub(r"\S+\.sqlite\b", "", text, flags=re.I)
    text = re.sub(r"\[[a-z_]+_omitted\]", "", text, flags=re.I)
    text = re.sub(r"\b[a-z_]+_omitted\b", "", text, flags=re.I)
    if not content:
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def _agentic_v9_public_sanitize_value(value, *, key="", depth=0):
    if depth > 12:
        return {}
    key_text = str(key or "")
    key_low = key_text.lower()
    if key_low in _AGENTIC_V9_PUBLIC_POINTER_KEYS:
        return None
    if isinstance(value, dict):
        out = {}
        for child_key, child_value in value.items():
            sanitized = _agentic_v9_public_sanitize_value(
                child_value,
                key=str(child_key),
                depth=depth + 1,
            )
            if sanitized not in (None, "", [], {}):
                out[str(child_key)] = sanitized
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            sanitized = _agentic_v9_public_sanitize_value(item, key=key_text, depth=depth + 1)
            if sanitized not in (None, "", [], {}):
                out.append(sanitized)
        return out
    if isinstance(value, str):
        return _agentic_v9_public_sanitize_text(
            value,
            content=_agentic_v9_public_content_key(key_text),
        )
    return value


def _agentic_v9_public_arguments(args):
    if not isinstance(args, dict):
        return {}
    return _agentic_v9_public_sanitize_value(args) or {}


def _agentic_v9_public_history_row(row):
    row = _agentic_v9_as_dict(row)
    decision = _agentic_v9_as_dict(row.get("decision"))
    result = _agentic_v9_as_dict(row.get("tool_result"))
    if not result and row.get("tool"):
        result = row
    tool = result.get("tool") or decision.get("tool") or row.get("tool")

    def public_summary(value):
        text = _agentic_v9_clip_text(value, 1200)
        return _agentic_v9_public_sanitize_text(text)

    public = {
        "step": row.get("step"),
        "action": decision.get("action") or row.get("action"),
        "tool": tool,
        "ok": result.get("ok") if result else row.get("ok"),
        "reason": _agentic_v9_clip_text(decision.get("reason") or row.get("reason"), 700),
        "arguments": _agentic_v9_public_arguments(
            decision.get("arguments") if isinstance(decision.get("arguments"), dict) else row.get("arguments")
        ),
        "path": result.get("path") or row.get("path"),
        "count": result.get("count") or row.get("count"),
        "total_matches": result.get("total_matches") or row.get("total_matches"),
        "items_total": result.get("items_total") or row.get("items_total"),
        "paths_total": result.get("paths_total") or row.get("paths_total"),
        "returncode": result.get("returncode") or row.get("returncode"),
        "guard_type": result.get("guard_type") or row.get("guard_type"),
        "violations": result.get("violations") or row.get("violations"),
        "summary": public_summary(result.get("summary") or row.get("summary")),
    }
    if tool == "repo_read":
        items = []
        source_items = _agentic_v9_as_list(result.get("items") or row.get("items"))
        for item in source_items[:80]:
            item = _agentic_v9_as_dict(item)
            content = item.get("content")
            items.append({
                "ok": item.get("ok"),
                "path": item.get("path"),
                "line_count": item.get("line_count"),
                "truncated": item.get("truncated"),
                "content_chars": len(content) if isinstance(content, str) else item.get("content_chars"),

                "error": item.get("error"),
            })
        public["items"] = items
    elif tool == "repo_propose_code_edit":
        for key in (
            "kind", "target_file", "edit_kind", "rationale",
            "source_writes_performed", "patch_application_performed",
            "manual_review_required", "validation_commands",
            "unified_diff", "structured_operations", "errors", "warnings",
            "target_metadata", "ast_evidence",
        ):
            value = result.get(key) if result else row.get(key)
            if value not in (None, "", [], {}):
                public[key] = value
    elif tool == "planner_scratchpad_read":
        mode = result.get("mode") or row.get("mode")
        if mode:
            public["mode"] = mode
        items = _agentic_v9_as_list(result.get("items") or row.get("items"))
        if items:
            public["items"] = [
                _agentic_v9_clean({
                    "section": _agentic_v9_as_dict(item).get("section"),
                    "window_start": _agentic_v9_as_dict(item).get("window_start"),
                    "window_end": _agentic_v9_as_dict(item).get("window_end"),
                    "full_chars": _agentic_v9_as_dict(item).get("full_chars"),
                    "window_chars": _agentic_v9_as_dict(item).get("window_chars"),
                    "complete": _agentic_v9_as_dict(item).get("complete"),
                    "has_more_before": _agentic_v9_as_dict(item).get("has_more_before"),
                    "has_more_after": _agentic_v9_as_dict(item).get("has_more_after"),
                    "sha256": _agentic_v9_as_dict(item).get("sha256"),
                    "window_sha256": _agentic_v9_as_dict(item).get("window_sha256"),
                    "text": _agentic_v9_as_dict(item).get("text"),
                })
                for item in items[:80]
            ]
    return _agentic_v9_clean(public)


def _agentic_v9_public_result_for_30b(result):
    if not isinstance(result, dict):
        return result
    public = dict(result)
    history = result.get("history")
    if isinstance(history, list):
        public["history_count"] = len(history)
        public["history"] = [_agentic_v9_public_history_row(row) for row in history]
        public["history_schema"] = "agentic_terminal_public_history_ledger.v1"
        public["raw_history_not_inlined"] = True
    memory_write = public.get("controller_memory_write")
    if isinstance(memory_write, dict):
        public["controller_memory_write"] = {
            k: memory_write.get(k)
            for k in ("ok", "tool", "kind", "tag", "record_id", "chars", "sha256", "target_key")
            if memory_write.get(k) not in (None, "", [], {})
        }
    return _agentic_v9_clean(_agentic_v9_public_sanitize_value(public) or {})


def _agentic_v9_context_keys():
    return ("tool_context_for_30b", "structured_result_for_30b", "agent_context_for_30b", "tool_result_for_30b", "result")


def _agentic_v9_extract_context(decoded):
    if not isinstance(decoded, dict):
        return "", {}
    for key in _agentic_v9_context_keys():
        parsed = _agentic_v9_parse_jsonish(decoded.get(key))
        if isinstance(parsed, dict):
            if (
                parsed.get("type")
                or parsed.get("schema")
                or parsed.get("history")
                or parsed.get("successful_tool_turns")
                or parsed.get("planner")
                or parsed.get("evidence_bundle")
            ):
                return key, parsed
    return "", {}


def _agentic_v9_explicit_tool_context(decoded):
    if not isinstance(decoded, dict):
        return {}
    parsed = _agentic_v9_parse_jsonish(decoded.get("tool_context_for_30b"))
    return parsed if isinstance(parsed, dict) else {}


def _agentic_v9_extract_result(decoded, context):
    for source in (decoded, context):
        if isinstance(source, dict) and isinstance(source.get("result"), dict):
            return source.get("result")
    return context if isinstance(context, dict) else {}


def _agentic_v9_extract_history(context, result, decoded):
    candidates = []
    for source in (context, result, decoded):
        if isinstance(source, dict):
            candidates.append(source.get("successful_tool_turns"))
            nested = source.get("result")
            if isinstance(nested, dict):
                candidates.append(nested.get("successful_tool_turns"))
    for source in (result, context, decoded):
        if isinstance(source, dict):
            candidates += [
                source.get("validated_tool_calls"),
                source.get("history"),
                source.get("executed_tools"),
                source.get("validated_steps"),
                source.get("tool_results"),
            ]
            nested = source.get("result")
            if isinstance(nested, dict):
                candidates += [
                    nested.get("validated_tool_calls"),
                    nested.get("history"),
                    nested.get("executed_tools"),
                ]
    for c in candidates:
        if isinstance(c, list) and c:
            return c
    return []


def _agentic_v9_extract_evidence_contract(context, result):
    for source in (result, context):
        if not isinstance(source, dict):
            continue
        for key in ("evidence_contract_at_terminal", "evidence_contract_at_finish", "evidence_contract", "contract"):
            if isinstance(source.get(key), dict):
                return source.get(key)
    return {}


def _agentic_v9_extract_planner(context, result):
    for source in (result, context):
        if isinstance(source, dict) and isinstance(source.get("planner"), dict):
            return source.get("planner")
    return {}


def _agentic_v9_extract_final_decision(context, result, decoded):
    for source in (result, context, decoded):
        if not isinstance(source, dict):
            continue
        for key in ("planner_decision", "final_decision"):
            if isinstance(source.get(key), dict):
                return source.get(key)
    planner = _agentic_v9_extract_planner(context, result)
    return planner.get("final_decision") if isinstance(planner.get("final_decision"), dict) else {}


def _agentic_v9_artifacts(decoded, context, result):
    artifacts = {}
    for source in (decoded, context, result):
        if not isinstance(source, dict):
            continue
        if isinstance(source.get("artifacts"), dict):
            artifacts.update(source["artifacts"])
        for key in ("final_path", "final_markdown_path", "events_path", "job_url", "final_json", "final_markdown", "events_ndjson"):
            if source.get(key):
                artifacts[key] = source.get(key)
    paths = []
    for key in ("final_path", "final_markdown_path", "events_path", "final_json", "final_markdown", "events_ndjson"):
        if artifacts.get(key) and artifacts[key] not in paths:
            paths.append(artifacts[key])
    if paths:
        artifacts["artifact_paths"] = paths
    return artifacts


def _agentic_v9_read_json_artifact(path_value):
    path = str(path_value or "").strip().strip('"')
    if not path:
        return None, {"loaded": False, "reason": "empty_path"}
    try:
        p = _agentic_v9_Path(path)
        if not p.exists() or not p.is_file():
            return None, {"loaded": False, "path": path, "reason": "missing_or_not_file"}
        raw = p.read_text(encoding="utf-8", errors="replace")
        parsed = _agentic_v9_parse_jsonish(raw)
        if not isinstance(parsed, dict):
            return None, {"loaded": False, "path": path, "reason": "not_json", "chars": len(raw)}
        return parsed, {"loaded": True, "path": path, "chars": len(raw), "truncated": False}
    except BaseException as exc:
        return None, {"loaded": False, "path": path, "reason": type(exc).__name__, "error": str(exc)}


def _agentic_v9_full_completed_payload(decoded):
    if not isinstance(decoded, dict):
        return decoded
    status = str(decoded.get("status") or "").strip()
    successful = (status == "completed" or decoded.get("job_ok") is True)
    if not successful or decoded.get("ok") is False or decoded.get("job_ok") is False:
        return decoded
    candidates = []
    for key in ("final_path", "final_json"):
        value = decoded.get(key)
        if value:
            candidates.append(value)
    artifacts = decoded.get("artifacts")
    if isinstance(artifacts, list):
        for value in artifacts:
            if isinstance(value, str) and value.lower().endswith("final.json"):
                candidates.append(value)
    for path_value in candidates:
        loaded, _load_meta = _agentic_v9_read_json_artifact(path_value)
        if not isinstance(loaded, dict):
            continue
        loaded_status = str(loaded.get("status") or status or "").strip()
        loaded_successful = loaded_status == "completed" or loaded.get("job_ok") is True
        if not loaded_successful or loaded.get("ok") is False or loaded.get("job_ok") is False:
            continue
        merged = dict(loaded)
        for key in ("ok", "job_ok", "service", "job_id", "status", "goal"):
            if merged.get(key) in (None, "", [], {}) and decoded.get(key) not in (None, "", [], {}):
                merged[key] = decoded.get(key)
        if merged.get("job_ok") in (None, "") and merged.get("status") == "completed":
            merged["job_ok"] = True
        if merged.get("service") in (None, ""):
            merged["service"] = decoded.get("service") or "vulkan_agent"
        return merged
    return decoded


_AGENTIC_V9_TERMINAL_STATUSES = {
    "completed",
    "blocked_needs_attention",
    "blocked_needs_consent",
    "failed",
    "failed_tool_error",
    "failed_planner_error",
    "max_steps_reached",
    "max_steps",
    "cancelled",
}


def _agentic_v9_is_terminal_status(status):
    return str(status or "").strip() in _AGENTIC_V9_TERMINAL_STATUSES


def _agentic_v9_full_terminal_payload(decoded):
    if not isinstance(decoded, dict):
        return decoded
    status = str(decoded.get("status") or "").strip()
    if not _agentic_v9_is_terminal_status(status):
        return decoded
    candidates = []
    for key in ("final_path", "final_json"):
        value = decoded.get(key)
        if value:
            candidates.append(value)
    artifacts = decoded.get("artifacts")
    if isinstance(artifacts, dict):
        for key in ("final_json", "final_path"):
            value = artifacts.get(key)
            if value:
                candidates.append(value)
    elif isinstance(artifacts, list):
        for value in artifacts:
            if isinstance(value, str) and value.lower().endswith("final.json"):
                candidates.append(value)
    for path_value in candidates:
        loaded, _load_meta = _agentic_v9_read_json_artifact(path_value)
        if not isinstance(loaded, dict):
            continue
        loaded_status = str(loaded.get("status") or status or "").strip()
        if not _agentic_v9_is_terminal_status(loaded_status):
            continue
        merged = dict(loaded)
        for key in ("ok", "job_ok", "service", "job_id", "status", "goal"):
            if merged.get(key) in (None, "", [], {}) and decoded.get(key) not in (None, "", [], {}):
                merged[key] = decoded.get(key)
        if merged.get("service") in (None, ""):
            merged["service"] = decoded.get("service") or "vulkan_agent"
        return merged
    return decoded


def _agentic_v9_tool_name(row):
    row = _agentic_v9_as_dict(row)
    if row.get("tool_name"):
        return str(row.get("tool_name"))
    if row.get("tool"):
        return str(row.get("tool"))
    tool_response = row.get("tool_response")
    if isinstance(tool_response, dict) and tool_response.get("tool"):
        return str(tool_response.get("tool"))
    for key in ("tool_call", "decision"):
        obj = row.get(key)
        if isinstance(obj, dict) and (obj.get("tool_name") or obj.get("tool") or obj.get("name")):
            return str(obj.get("tool_name") or obj.get("tool") or obj.get("name"))
    return ""


def _agentic_v9_args(row):
    row = _agentic_v9_as_dict(row)
    for key in ("args", "arguments"):
        if isinstance(row.get(key), dict):
            return row[key]
    for key in ("tool_call", "decision"):
        obj = row.get(key)
        if isinstance(obj, dict):
            for akey in ("args", "arguments"):
                if isinstance(obj.get(akey), dict):
                    return obj[akey]
    return {}


def _agentic_v9_result(row):
    row = _agentic_v9_as_dict(row)
    for key in ("tool_response", "result", "tool_result", "output"):
        if isinstance(row.get(key), dict):
            return row[key]
    if row.get("ok") is not None and _agentic_v9_tool_name(row):
        return row
    return {}


def _agentic_v9_artifact_path(row, result):
    row = _agentic_v9_as_dict(row)
    result = _agentic_v9_as_dict(result)
    for source in (row, result):
        for key in ("artifact", "artifact_path", "path_to_artifact"):
            if isinstance(source.get(key), str):
                return source[key]
        if isinstance(source.get("artifact"), dict):
            art = source["artifact"]
            if art.get("path"):
                return art["path"]
    return ""


def _agentic_v9_normalized_call(row, idx):
    row = _agentic_v9_as_dict(row)
    tool = _agentic_v9_tool_name(row) or "unknown_tool"
    args = _agentic_v9_args(row)
    result = _agentic_v9_result(row)
    artifact = _agentic_v9_artifact_path(row, result)
    loaded, load_meta = _agentic_v9_read_json_artifact(artifact) if artifact else (None, {})
    if isinstance(loaded, dict):
        result = {**result, **loaded} if isinstance(result, dict) else loaded
    ok = row.get("ok")
    if ok is None:
        ok = result.get("ok")
    if row.get("validated") is not None:
        validated = bool(row.get("validated"))
    else:
        validated = bool(ok) if ok is not None else True
    return _agentic_v9_clean({
        "schema": "openwebui.validated_tool_call_observation.v1",
        "step": row.get("step") or result.get("step") or idx + 1,
        "validated": validated,
        "tool_name": tool,
        "arguments": args,
        "reason": row.get("reason") or _agentic_v9_as_dict(row.get("decision")).get("reason"),
        "result": result,
        "artifact": artifact,
        "artifact_load": load_meta,
    })


def _agentic_v9_add_unique(items, item, key="path"):
    if not item:
        return
    if isinstance(item, dict) and key in item:
        if not any(isinstance(x, dict) and x.get(key) == item.get(key) for x in items):
            items.append(item)
    elif item not in items:
        items.append(item)


def _agentic_v9_build_evidence(calls, evidence_contract):
    bundle = {
        "schema": "openwebui.agentic_evidence_index.v1",
        "repo_trees": [],
        "repo_file_lists": [],
        "repo_file_reads": [],
        "repo_searches": [],
        "files": [],
        "directories": [],
        "evidence_contract": evidence_contract or {},
    }

    def add_file(path, **meta):
        if path:
            item = {"path": str(path)}
            item.update({k: v for k, v in meta.items() if v not in (None, "", [], {})})
            _agentic_v9_add_unique(bundle["files"], item)

    def add_dir(path, **meta):
        if path:
            item = {"path": str(path)}
            item.update({k: v for k, v in meta.items() if v not in (None, "", [], {})})
            _agentic_v9_add_unique(bundle["directories"], item)

    for call in calls:
        if call.get("validated") is False:
            continue
        result = _agentic_v9_as_dict(call.get("result"))
        if result.get("ok") is False:
            continue
        tool = str(call.get("tool_name") or "")
        args = _agentic_v9_as_dict(call.get("arguments"))

        entries = _agentic_v9_as_list(result.get("entries") or result.get("entries_preview"))
        if tool in {"repo_tree", "repo_tree_files", "tree"} or entries:
            bundle["repo_trees"].append(_agentic_v9_clean({
                "tool_step": call.get("step"),
                "path": result.get("path") or args.get("path"),
                "entries_total": result.get("entries_total") or result.get("count"),
                "entries_preview": entries[:_AGENTIC_V9_MAX_ITEMS],
                "truncated": result.get("truncated"),
            }))
            for e in entries[:_AGENTIC_V9_MAX_ITEMS]:
                if isinstance(e, dict):
                    p = e.get("path") or e.get("name")
                    kind = e.get("kind") or e.get("type")
                    if kind in {"dir", "directory"}:
                        add_dir(p, source_tool="repo_tree")
                    else:
                        add_file(p, source_tool="repo_tree", size_bytes=e.get("size_bytes") or e.get("size"))

        paths = _agentic_v9_as_list(result.get("paths") or result.get("paths_preview"))
        files_preview = _agentic_v9_as_list(result.get("files") or result.get("files_preview"))
        if tool in {"repo_list_files", "repo_file_list", "list_files"} or paths or files_preview:
            bundle["repo_file_lists"].append(_agentic_v9_clean({
                "tool_step": call.get("step"),
                "path": result.get("path") or args.get("path"),
                "total_matches": result.get("total_matches") or result.get("paths_total") or result.get("files_total") or result.get("count"),
                "limit": result.get("limit"),
                "truncated": result.get("truncated"),
                "paths": paths[:_AGENTIC_V9_MAX_ITEMS],
                "files_preview": files_preview[:_AGENTIC_V9_MAX_ITEMS],
            }))
            for p in paths[:_AGENTIC_V9_MAX_ITEMS]:
                if isinstance(p, str):
                    add_file(p, source_tool="repo_list_files")
            for f in files_preview[:_AGENTIC_V9_MAX_ITEMS]:
                if isinstance(f, dict):
                    add_file(f.get("path"), source_tool="repo_list_files", size_bytes=f.get("size_bytes") or f.get("size"))

        read_items = []
        for item in _agentic_v9_as_list(result.get("items")):
            if isinstance(item, dict):
                if item.get("ok") is False:
                    continue
                content_key = next(
                    (key for key in ("content", "content_preview", "text", "body", "preview") if item.get(key)),
                    "",
                )
                content = item.get(content_key) if content_key else ""
                read_item = _agentic_v9_clean({
                    "path": item.get("path"),
                    "ok": item.get("ok"),
                    "line_start": item.get("line_start") or item.get("start_line"),
                    "line_end": item.get("line_end") or item.get("end_line"),
                    "line_count": item.get("line_count"),
                    "truncated": item.get("truncated"),
                    "content_source": content_key,
                    "preview_only": content_key in {"content_preview", "preview"},
                    "content_excerpt": _agentic_v9_clip_text(content, BRIDGE_OPENWEBUI_INLINE_FILE_CHARS) if content else None,
                })
                read_items.append(read_item)
                add_file(item.get("path"), source_tool="repo_read", line_count=item.get("line_count"), truncated=item.get("truncated"))
        if not read_items and result.get("path") and (tool in {"repo_read", "repo_file_read", "read_file"}):
            content_key = next(
                (key for key in ("content", "content_preview", "text", "body", "preview") if result.get(key)),
                "",
            )
            content = result.get(content_key) if content_key else ""
            read_items.append(_agentic_v9_clean({
                "path": result.get("path"),
                "ok": result.get("ok"),
                "line_start": result.get("line_start") or result.get("start_line"),
                "line_end": result.get("line_end") or result.get("end_line"),
                "line_count": result.get("line_count"),
                "truncated": result.get("truncated"),
                "content_source": content_key,
                "preview_only": content_key in {"content_preview", "preview"},
                "content_excerpt": _agentic_v9_clip_text(content, BRIDGE_OPENWEBUI_INLINE_FILE_CHARS) if content else None,
            }))
            add_file(result.get("path"), source_tool="repo_read", line_count=result.get("line_count"), truncated=result.get("truncated"))
        if read_items:
            bundle["repo_file_reads"].append({"tool_step": call.get("step"), "items": read_items[:_AGENTIC_V9_MAX_ITEMS]})

        matches = _agentic_v9_as_list(result.get("matches") or result.get("results"))
        if tool in {"repo_search", "search"} or matches:
            bundle["repo_searches"].append(_agentic_v9_clean({
                "tool_step": call.get("step"),
                "query": result.get("query") or args.get("query"),
                "matches": matches[:_AGENTIC_V9_MAX_ITEMS],
                "count": result.get("count") or len(matches),
                "truncated": result.get("truncated"),
            }))

    for p in _agentic_v9_as_list(evidence_contract.get("known_paths_from_latest_repo_list_files"))[:_AGENTIC_V9_MAX_ITEMS]:
        if isinstance(p, str):
            if "." not in p.split("/")[-1]:
                add_dir(p, source_tool="evidence_contract")
            else:
                add_file(p, source_tool="evidence_contract")

    return _agentic_v9_clean(bundle)


def _agentic_v9_extract_initial_orientation_surface(context, result, decoded, evidence_contract):
    for source in (context, result, decoded, evidence_contract):
        if isinstance(source, dict) and isinstance(source.get("initial_orientation_surface"), dict):
            return source.get("initial_orientation_surface")
    return {}


def _agentic_v9_build_observation_object(decoded):
    context_key, context = _agentic_v9_extract_context(decoded)
    result = _agentic_v9_extract_result(decoded, context)
    history = _agentic_v9_extract_history(context, result, decoded)
    calls = [_agentic_v9_normalized_call(row, idx) for idx, row in enumerate(history) if isinstance(row, dict)]
    planner = _agentic_v9_extract_planner(context, result)
    final_decision = _agentic_v9_extract_final_decision(context, result, decoded)
    evidence_contract = _agentic_v9_extract_evidence_contract(context, result)
    artifacts = _agentic_v9_artifacts(decoded, context, result)
    evidence = _agentic_v9_build_evidence(calls, evidence_contract)
    initial_orientation = _agentic_v9_extract_initial_orientation_surface(
        context,
        result,
        decoded,
        evidence_contract,
    )

    job = _agentic_v9_as_dict(context.get("job")) or _agentic_v9_as_dict(result.get("job"))
    status = decoded.get("status") or job.get("status") or result.get("status")
    goal = decoded.get("goal") or job.get("goal") or _agentic_v9_as_dict(result.get("response_to_tool_call")).get("goal")
    tool_name = decoded.get("tool_name") or decoded.get("tool_result_for") or result.get("name") or "vulkan_helper"
    completed = status == "completed" or decoded.get("job_ok") is True
    blocked = status == "blocked_needs_attention" or decoded.get("job_ok") is False
    internal_final = (
        decoded.get("answer_for_30b")
        or decoded.get("final_summary")
        or decoded.get("summary_for_30b")
        or context.get("final_answer")
        or result.get("internal_planner_final_text")
        or result.get("final_summary")
        or final_decision.get("final_answer")
        or ""
    )
    candidates = [c for c in _agentic_v9_as_list(evidence_contract.get("candidate_next_actions"))[:12] if isinstance(c, dict)]

    observation = {
        "schema": "openwebui.tool_observation_for_reasoning.v1",
        "schema_version": "agentic-loop-v9",
        "role_semantics": "tool_observation_not_assistant_answer",
        "tool_name": tool_name,
        "status": status,
        "ok": decoded.get("ok"),
        "job": {
            "job_id": decoded.get("job_id") or job.get("job_id") or result.get("job_id"),
            "job_url": decoded.get("job_url") or artifacts.get("job_url"),
            "goal": goal,
            "bridge_status": decoded.get("bridge_status"),
            "bridge_waited_for_agent": decoded.get("bridge_waited_for_agent"),
            "bridge_forwarded_to_vulkan": decoded.get("bridge_forwarded_to_vulkan"),
        },
        "assistant_directive": {
            "this_message_is_tool_output": True,
            "do_not_print_or_echo_raw_json": True,
            "do_not_wrap_the_tool_output_as_the_final_answer": True,
            "must_synthesize_final_user_answer": bool(completed),
            "if_blocked_explain_blocker_from_validation_evidence": bool(blocked),
            "use_evidence_before_internal_final_text": True,
            "answer_language": "match_user_language",
            "when_completed": "Answer the user now from evidence_index and validated_tool_calls. Do not ask whether to proceed.",
            "when_more_detail_needed": "Call vulkan_helper again using continuation_surface.call_protocol; do not invent missing repository facts.",
        },
        "answer_task": {
            "user_goal": goal,
            "task_type": "repository_or_code_analysis",
            "required_output": "natural_language_analysis_not_raw_json",
            "required_sections_for_repo_analysis": [
                "cosa_è_stato_verificato",
                "struttura_principale_osservata",
                "file_o_moduli_chiave_con_path",
                "evidenza_usata",
                "limiti_troncamenti_o_parti_non_lette",
                "prossima_call_tool_suggerita_solo_se_serve",
            ],
            "citation_policy": "cite paths/steps from evidence_index; never cite files not present in evidence_index",
        },
        "continuation_surface": {
            "tool_has_more_surface": True,
            "public_tool": "vulkan_helper",
            "current_call_is_complete": completed or blocked,
            "outer_model_may_call_tool_again": True,
            "call_protocol": {
                "action": "start",
                "request": "<full user request or precise follow-up>",
                "function": "repo_status | repo_capabilities | repo_tree | repo_read | repo_list_files | repo_search",
            },
            "call_examples": [
                {"action": "start", "function": "repo_status", "request": "analyze ia_carmine entrypoint and main execution flow"},
                {"action": "start", "function": "repo_status", "request": "read and analyze WORKFLOW.md and AGENTS.md"},
                {"action": "start", "function": "repo_status", "request": "deep-dive docs/AI_DOCS_ENTRYPOINT.md and summarize architecture constraints"},
            ],
            "candidate_next_actions_from_inner_planner": candidates,
        },
        "validated_tool_calls": calls,
        "evidence_index": evidence,
        "initial_orientation_surface": initial_orientation,
        "planner": _agentic_v9_clean({
            "planner_model": _agentic_v9_as_dict(planner).get("planner_model") or job.get("planner_model"),
            "decisions": _agentic_v9_as_dict(planner).get("decisions"),
            "validation_rejections": _agentic_v9_as_dict(planner).get("validation_rejections"),
            "terminal_decision": final_decision,
        }),
        "evidence_contract_at_terminal": evidence_contract,
        "internal_planner_final_text": internal_final,
        "artifacts": artifacts,
        "transport_diagnostics": {
            "context_source": context_key,
            "validated_tool_call_count": len(calls),
            "repo_tree_count": len(evidence.get("repo_trees", [])),
            "repo_file_list_count": len(evidence.get("repo_file_lists", [])),
            "repo_file_read_count": len(evidence.get("repo_file_reads", [])),
            "known_file_count": len(evidence.get("files", [])),
            "known_directory_count": len(evidence.get("directories", [])),
            "artifact_paths_loaded": sum(1 for c in calls if _agentic_v9_as_dict(c.get("artifact_load")).get("loaded")),
            "created_unix": _agentic_v9_time.time(),
        },
    }
    observation["transport_diagnostics"]["json_chars"] = _agentic_v9_json_len(observation)
    observation["transport_diagnostics"]["json_sha256"] = _agentic_v9_sha256_json(observation)
    return _agentic_v9_clean(observation)


def _agentic_v9_compact_json(observation):
    raw = _agentic_v9_json_dumps(observation, indent=2)
    if len(raw) <= _AGENTIC_V9_OBSERVATION_JSON_CHARS:
        return raw, False
    ev = _agentic_v9_as_dict(observation.get("evidence_index"))
    slim = dict(observation)
    slim["validated_tool_calls"] = _agentic_v9_as_list(observation.get("validated_tool_calls"))[:40]
    slim["evidence_index"] = {
        **ev,
        "repo_trees": _agentic_v9_as_list(ev.get("repo_trees"))[:5],
        "repo_file_lists": _agentic_v9_as_list(ev.get("repo_file_lists"))[:20],
        "repo_file_reads": _agentic_v9_as_list(ev.get("repo_file_reads"))[:20],
        "repo_searches": _agentic_v9_as_list(ev.get("repo_searches"))[:20],
        "files": _agentic_v9_as_list(ev.get("files"))[:300],
        "directories": _agentic_v9_as_list(ev.get("directories"))[:120],
    }
    td = _agentic_v9_as_dict(slim.get("transport_diagnostics"))
    td["observation_json_truncated_for_openwebui_context"] = True
    td["full_result_available_in_artifacts"] = True
    slim["transport_diagnostics"] = td
    return _agentic_v9_json_dumps(_agentic_v9_clean(slim), indent=2), True


def _agentic_v9_build_protocol_text(decoded):
    observation = _agentic_v9_build_observation_object(decoded)
    json_text, truncated = _agentic_v9_compact_json(observation)
    diag = _agentic_v9_as_dict(observation.get("transport_diagnostics"))
    job = _agentic_v9_as_dict(observation.get("job"))
    completed = observation.get("status") == "completed" or observation.get("job_ok") is True
    blocked = observation.get("status") == "blocked_needs_attention" or observation.get("job_ok") is False
    if completed:
        required_action = "Produce a grounded answer to the user now. Do not print the JSON below. Use it as evidence."
    elif blocked:
        required_action = "Explain the blocker and exact evidence/validator state. Do not print the JSON below."
    else:
        required_action = "Use the observation to decide whether to answer or call vulkan_helper again. Do not print the JSON below verbatim."

    lines = [
        "TOOL OBSERVATION FOR OUTER MODEL - vulkan_helper",
        "This is the result of your completed OpenWebUI tool call, not the final assistant answer.",
        "Required assistant behavior: " + required_action,
        "",
        "USER_GOAL:",
        str(job.get("goal") or ""),
        "",
        "HOW TO USE THIS TOOL OUTPUT:",
        "1. Parse the JSON object below internally as evidence.",
        "2. Do NOT echo, pretty-print, or expose the raw JSON as your answer.",
        "3. Answer in the user's language using evidence_index and validated_tool_calls.",
        "4. If evidence is insufficient, call vulkan_helper again using continuation_surface.call_protocol.",
        "5. Never invent file paths, sizes, contents, or conclusions outside evidence_index.",
        "",
        "OBSERVATION SUMMARY:",
        "- status: " + str(observation.get("status")),
        "- job_id: " + str(job.get("job_id")),
        "- validated_tool_calls: " + str(diag.get("validated_tool_call_count")),
        "- repo_trees: " + str(diag.get("repo_tree_count")),
        "- repo_file_lists: " + str(diag.get("repo_file_list_count")),
        "- repo_file_reads: " + str(diag.get("repo_file_read_count")),
        "- artifact_paths_loaded: " + str(diag.get("artifact_paths_loaded")),
        "- observation_json_truncated: " + str(truncated).lower(),
        "",
        "BEGIN STRUCTURED TOOL OBSERVATION JSON",
        "```json",
        json_text,
        "```",
        "END STRUCTURED TOOL OBSERVATION JSON",
        "",
        "NOW ANSWER THE USER FROM THE TOOL OBSERVATION. DO NOT OUTPUT THE JSON ITSELF.",
        "",
    ]
    return "\n".join(lines)


def _agentic_v9_split_final_and_evidence(answer):
    text = str(answer or "").strip()
    marker = "OpenWebUI follow-up evidence from executed tools:"
    if marker not in text:
        return text, ""
    final_text, evidence_text = text.split(marker, 1)
    return final_text.strip(), marker + "\n" + evidence_text.strip()


def _agentic_v9_content_view_blocks(text):
    blocks = []
    pattern = re.compile(
        r"(?ms)(?:^|\n)\s+- path=(?P<meta>[^\n]+)\n````text\n(?P<content>.*?)(?:\n````)(?=\n\s+- path=|\n- artifact files|\Z)"
    )
    for match in pattern.finditer(str(text or "")):
        meta = match.group("meta").strip()
        path = meta.split(" lines=", 1)[0].strip()
        blocks.append({
            "path": path,
            "meta": meta,
            "content": match.group("content").strip("\n"),
        })
    return blocks


def _agentic_v9_inline_content_view(after):
    blocks = _agentic_v9_content_view_blocks(after)
    if not blocks:
        return ""

    remaining = max(0, BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS)
    parts = []
    for block in blocks:
        if remaining <= 0:
            parts.append("- PUBLIC_RESULT_NOT_SELF_CONTAINED: additional repo_read content is not inline because the evidence budget is exhausted.")
            break
        content = block["content"]
        section = [
            f"  - path={block['meta']}",
            "````text",
            content,
            "````",
        ]
        rendered = "\n".join(section)
        if len(rendered) > remaining:
            parts.append(
                "- PUBLIC_RESULT_NOT_SELF_CONTAINED: "
                f"{block['path']} was not included inline because the whole file would exceed the evidence budget. "
                "No partial/truncated file body was provided."
            )
            break
        parts.append(rendered)
        remaining -= len(rendered)
    return "\n".join(parts)


def _agentic_v9_compact_outer_evidence(evidence_text):
    text = str(evidence_text or "").strip()
    if not text:
        return ""
    marker = "- repo_read content_view:"
    if marker not in text:
        return _compact_text(text, 12000)

    before, after = text.split(marker, 1)
    artifact_lines = []
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("- path=") or stripped.startswith("- C:\\") or "artifact=" in stripped:
            artifact_lines.append(line)
        if stripped.startswith("- artifact files with full tool results:"):
            artifact_lines.append(line)
    compact = before.rstrip()
    inline_view = _agentic_v9_inline_content_view(after)
    if inline_view:
        compact += "\n- repo_read content_view inline pack:"
        compact += "\n" + inline_view
    else:
        compact += "\n- repo_read content_view: unavailable in parsed inline evidence."
    return _compact_text(compact, BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS)


def _agentic_v9_repo_path(value):
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text or "."


def _agentic_v9_path_under(path, area):
    p = _agentic_v9_repo_path(path)
    a = _agentic_v9_repo_path(area).rstrip("/")
    if a in {"", "."}:
        return False
    return p == a or p.startswith(a + "/")


def _agentic_v9_unique_texts(values):
    out = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _agentic_v9_entry_label(entry):
    if isinstance(entry, dict):
        path = entry.get("path") or entry.get("name") or entry.get("file")
        parts = [_agentic_v9_repo_path(path)]
        kind = entry.get("kind") or entry.get("type")
        if kind:
            parts.append(f"kind={kind}")
        size = entry.get("size_bytes") or entry.get("size")
        if size not in (None, ""):
            parts.append(f"size={size}")
        return " | ".join(str(p) for p in parts if p not in (None, ""))
    return str(entry)


def _agentic_v9_append_paths(lines, paths, *, empty="- nessun path disponibile"):
    values = _agentic_v9_unique_texts(paths)
    if not values:
        lines.append(empty)
        return
    for path in values:
        lines.append(f"- {path}")


def _agentic_v9_collect_read_paths(evidence):
    paths = []
    for read_group in _agentic_v9_as_list(_agentic_v9_as_dict(evidence).get("repo_file_reads")):
        for item in _agentic_v9_as_list(_agentic_v9_as_dict(read_group).get("items")):
            item = _agentic_v9_as_dict(item)
            if item.get("path"):
                paths.append(_agentic_v9_repo_path(item.get("path")))
    return _agentic_v9_unique_texts(paths)


def _agentic_v9_evidence_limits(evidence, initial_orientation):
    evidence = _agentic_v9_as_dict(evidence)
    initial_orientation = _agentic_v9_as_dict(initial_orientation)
    limits = []
    for tree in _agentic_v9_as_list(evidence.get("repo_trees")):
        tree = _agentic_v9_as_dict(tree)
        if tree.get("truncated") is True:
            limits.append(f"- repo_tree truncated=true: path={tree.get('path') or '.'}")
    for file_list in _agentic_v9_as_list(evidence.get("repo_file_lists")):
        file_list = _agentic_v9_as_dict(file_list)
        if file_list.get("truncated") is True:
            limits.append(
                "- repo_list_files truncated=true: "
                f"area={file_list.get('path') or '.'} count={file_list.get('total_matches')}"
            )
    preview_only = []
    for read_group in _agentic_v9_as_list(evidence.get("repo_file_reads")):
        for item in _agentic_v9_as_list(_agentic_v9_as_dict(read_group).get("items")):
            item = _agentic_v9_as_dict(item)
            path = item.get("path")
            if item.get("truncated") is True:
                limits.append(f"- repo_read truncated=true: path={path}")
            if item.get("preview_only") is True and path:
                preview_only.append(_agentic_v9_repo_path(path))
    for path in _agentic_v9_unique_texts(preview_only):
        limits.append(f"- repo_read solo preview/content_preview: path={path}")

    read_paths = _agentic_v9_collect_read_paths(evidence)
    areas = _agentic_v9_unique_texts(_agentic_v9_as_list(initial_orientation.get("areas_listed")))
    for area in areas:
        if area in {"", "."}:
            continue
        if not any(_agentic_v9_path_under(path, area) for path in read_paths):
            limits.append(f"- area listata ma non approfondita con repo_read: {area}")
    return limits


def _agentic_v9_inline_json(value, limit=1200):
    try:
        text = _agentic_v9_json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except BaseException:
        text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 48)] + "... <truncated inline summary>"


def _agentic_v9_compact_sealed_text(value, limit):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if int(limit or 0) <= 0:
        return text
    if len(text) <= limit:
        return text
    suffix = (
        "\n\n[TRONCATO DAL LIMITE DI TRASPORTO OPENWEBUI: "
        "il pack inline ha superato il budget configurato; il contenuto oltre il limite "
        "non e' visibile al modello in questa risposta.]"
    )
    return text[:max(0, int(limit) - len(suffix))] + suffix


def _agentic_v9_planner_summary_from_text(text):
    text = str(text or "").strip()
    marker = "RISPOSTA SINTETICA DEL PLANNER:"
    if marker not in text:
        return text
    after = text.split(marker, 1)[1].lstrip()
    stops = [
        "\n\nINDICE OPERAZIONI RIUSCITE:",
        "\n\nINITIAL ORIENTATION SURFACE:",
        "\n\nREPO_TREE RIUSCITI:",
        "\n\nREPO_LIST_FILES RIUSCITI:",
        "\n\nREPO_READ RIUSCITI:",
        "\n\nLIMITI ESPLICITI:",
    ]
    end = len(after)
    for stop in stops:
        pos = after.find(stop)
        if pos >= 0:
            end = min(end, pos)
    return after[:end].strip()


def _agentic_v9_existing_inline_evidence_from_text(text):
    text = str(text or "")
    starts = [
        "INITIAL ORIENTATION SURFACE:",
        "REPO_TREE RIUSCITI:",
        "REPO_LIST_FILES RIUSCITI:",
        "REPO_READ RIUSCITI:",
        "OpenWebUI follow-up evidence from executed tools:",
    ]
    positions = [text.find(start) for start in starts if text.find(start) >= 0]
    if not positions:
        return ""
    start = min(positions)
    end = len(text)
    for stop in ("\n\nRIFERIMENTI SECONDARI", "\n\nFULL ARTIFACTS:", "\n\nBEGIN STRUCTURED TOOL OBSERVATION JSON"):
        pos = text.find(stop, start)
        if pos >= 0:
            end = min(end, pos)
    return text[start:end].strip()


def _agentic_v9_tool_args_summary(args):
    args = _agentic_v9_as_dict(args)
    if not args:
        return "{}"
    useful = {}
    for key in (
        "function", "path", "paths", "query", "pattern", "limit", "max_depth",
        "include_dirs", "start_line", "end_line", "request", "goal",
    ):
        if args.get(key) not in (None, "", [], {}):
            useful[key] = args.get(key)
    return _agentic_v9_inline_json(useful or args, 1000)


def _agentic_v9_result_summary(result):
    result = _agentic_v9_as_dict(result)
    bits = []
    for key in (
        "ok", "path", "entries_total", "count", "total_matches",
        "paths_total", "files_total", "limit", "line_count", "truncated",
    ):
        if result.get(key) not in (None, "", [], {}):
            bits.append(f"{key}={result.get(key)}")
    items = _agentic_v9_as_list(result.get("items"))
    if items:
        ok_items = [item for item in items if isinstance(item, dict) and item.get("ok") is not False]
        item_paths = [str(item.get("path")) for item in ok_items if item.get("path")]
        bits.append(f"items_ok={len(ok_items)}")
        if item_paths:
            bits.append("item_paths=" + _agentic_v9_inline_json(item_paths[:20], 1200))
    paths = _agentic_v9_as_list(result.get("paths") or result.get("paths_preview"))
    if paths:
        bits.append(f"paths_visible={len(paths)}")
    entries = _agentic_v9_as_list(result.get("entries") or result.get("entries_preview"))
    if entries:
        bits.append(f"entries_visible={len(entries)}")
    return " ".join(bits) if bits else "risultato disponibile nel dettaglio sotto"


def _agentic_v9_successful_calls(observation):
    calls = []
    for call in _agentic_v9_as_list(_agentic_v9_as_dict(observation).get("validated_tool_calls")):
        call = _agentic_v9_as_dict(call)
        result = _agentic_v9_as_dict(call.get("result"))
        tool = str(call.get("tool_name") or "").strip()
        if not tool or tool == "unknown_tool":
            continue
        if tool in {"controller_guard"}:
            continue
        if result.get("guard_type") or result.get("rejected_decision"):
            continue
        if call.get("validated") is False or result.get("ok") is not True:
            continue
        calls.append(call)
    return calls


def _agentic_v9_json_line(value):
    try:
        return _agentic_v9_json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except BaseException:
        return str(value)


def _agentic_v9_line_value(value):
    if isinstance(value, (dict, list)):
        return _agentic_v9_json_line(value)
    return str(value)


def _agentic_v9_append_successful_tool_index(lines, observation):
    calls = _agentic_v9_successful_calls(observation)
    lines.append("INDICE OPERAZIONI RIUSCITE:")
    if not calls:
        lines.append("- nessuna operazione riuscita disponibile nel payload.")
        return
    for call in calls:
        tool = call.get("tool_name") or "unknown_tool"
        args = _agentic_v9_tool_args_summary(call.get("arguments"))
        result = _agentic_v9_result_summary(call.get("result"))
        lines.append(f"- step={call.get('step')} tool={tool} args={args} result={result}")


def _agentic_v9_tool_block_header(call):
    tool = str(call.get("tool_name") or "unknown_tool")
    result = _agentic_v9_as_dict(call.get("result"))
    pieces = [
        f"step={call.get('step')}",
        f"tool={tool}",
        f"args={_agentic_v9_tool_args_summary(call.get('arguments'))}",
    ]
    for key in (
        "path", "count", "entries_total", "total_matches", "paths_total",
        "files_total", "limit", "line_count", "truncated", "returncode",
    ):
        if result.get(key) not in (None, "", [], {}):
            pieces.append(f"{key}={result.get(key)}")
    artifact = str(call.get("artifact") or "").strip()
    if artifact:
        pieces.append(f"artifact_metadata={artifact}")
    return " ".join(pieces)


def _agentic_v9_append_result_list(lines, title, values):
    lines.append(title)
    values = _agentic_v9_as_list(values)
    if not values:
        lines.append("- nessun valore disponibile nel risultato riuscito.")
        return
    for value in values:
        lines.append("- " + _agentic_v9_line_value(value))


def _agentic_v9_render_repo_tree_call(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    entries = _agentic_v9_as_list(result.get("entries") or result.get("entries_preview"))
    lines = [
        f"### TOOL RIUSCITO: {_agentic_v9_tool_block_header(call)}",
        f"path: {result.get('path') or args.get('path') or '.'}",
        f"entries_total: {result.get('entries_total') or result.get('count') or len(entries)}",
        f"truncated: {str(result.get('truncated')).lower() if result.get('truncated') is not None else 'unknown'}",
        "entries:",
    ]
    if not entries:
        lines.append("- nessuna entry inline disponibile nel risultato riuscito.")
        return lines
    for entry in entries:
        lines.append("- " + _agentic_v9_line_value(entry))
    return lines


def _agentic_v9_render_repo_list_files_call(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    paths = _agentic_v9_as_list(result.get("paths") or result.get("paths_preview"))
    files = _agentic_v9_as_list(result.get("files") or result.get("files_preview"))
    lines = [
        f"### TOOL RIUSCITO: {_agentic_v9_tool_block_header(call)}",
        f"path: {result.get('path') or args.get('path') or '.'}",
        f"count: {result.get('count') or result.get('paths_total') or result.get('files_total') or len(paths) or len(files)}",
        f"total_matches: {result.get('total_matches') or result.get('paths_total') or result.get('files_total') or len(paths) or len(files)}",
        f"limit: {result.get('limit') if result.get('limit') not in (None, '') else 'unknown'}",
        f"truncated: {str(result.get('truncated')).lower() if result.get('truncated') is not None else 'unknown'}",
        "paths:",
    ]
    if paths:
        for path in paths:
            lines.append("- " + str(path))
    elif files:
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                lines.append("- " + _agentic_v9_line_value(item))
            else:
                lines.append("- " + str(item))
    else:
        lines.append("- nessun path inline disponibile nel risultato riuscito.")
    return lines


def _agentic_v9_read_item_content(item):
    item = _agentic_v9_as_dict(item)
    if item.get("content") not in (None, ""):
        return str(item.get("content")), "content", False
    if item.get("content_preview") not in (None, ""):
        return str(item.get("content_preview")), "content_preview", True
    return "", "", False


def _agentic_v9_repo_result_path(value, fallback=""):
    value = _agentic_v9_as_dict(value)
    return value.get("repo_path") or value.get("path") or fallback


def _agentic_v9_render_repo_read_call(call):
    result = _agentic_v9_as_dict(call.get("result"))
    raw_items = _agentic_v9_as_list(result.get("items"))
    if not raw_items and _agentic_v9_repo_result_path(result):
        raw_items = [result]
    items = [
        _agentic_v9_as_dict(item)
        for item in raw_items
        if isinstance(item, dict) and item.get("ok") is not False
    ]
    lines = [f"### TOOL RIUSCITO: {_agentic_v9_tool_block_header(call)}"]
    if not items:
        lines.append("- nessun item repo_read inline disponibile nel risultato riuscito.")
        return lines
    for item in items:
        content, source, preview_only = _agentic_v9_read_item_content(item)
        meta = [
            f"path={_agentic_v9_repo_result_path(item)}",
            f"line_count={item.get('line_count') if item.get('line_count') not in (None, '') else 'unknown'}",
            f"truncated={str(item.get('truncated')).lower() if item.get('truncated') is not None else 'unknown'}",
            f"content_source={source or 'none'}",
            f"preview_only={str(preview_only).lower()}",
        ]
        if item.get("artifact"):
            meta.append(f"artifact_metadata={item.get('artifact')}")
        lines.append("- " + " ".join(meta))
        if content:
            lines.extend(["````text", content, "````"])
        else:
            lines.append("````text\n\n````")
    return lines


def _agentic_v9_generic_tool_payload(result):
    result = _agentic_v9_as_dict(result)
    useful_keys = (
        "summary", "returncode", "stdout", "stdout_tail", "stderr", "stderr_tail",
        "matches", "items", "paths", "files", "content", "text", "body",
        "result", "count", "total_matches", "limit", "truncated",
    )
    blocked_keys = {
        "artifact", "artifact_path", "path_to_artifact", "guard_type",
        "rejected_decision", "evidence_contract", "raw_event", "raw_events",
        "continuation_surface", "call_protocol", "call_examples",
        "transport_diagnostics", "json_sha256", "bridge_original_response_chars",
    }
    payload = {}
    for key in useful_keys:
        if key in blocked_keys:
            continue
        value = result.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    if payload:
        return payload
    return {
        key: value
        for key, value in result.items()
        if key not in blocked_keys and value not in (None, "", [], {})
    }


def _agentic_v9_code_edit_proposal_payload(result):
    result = _agentic_v9_as_dict(result)
    if result.get("artifact") and result.get("edit_kind") in {"unified_diff", "structured_edit"}:
        result = _agentic_v9_merge_loaded_artifact(result)
    payload = {
        "kind": result.get("kind"),
        "target_file": result.get("target_file"),
        "edit_kind": result.get("edit_kind"),
        "rationale": result.get("rationale"),
        "source_writes_performed": result.get("source_writes_performed"),
        "patch_application_performed": result.get("patch_application_performed"),
        "manual_review_required": result.get("manual_review_required"),
        "validation_commands": result.get("validation_commands"),
        "errors": result.get("errors"),
        "warnings": result.get("warnings"),
        "target_metadata": result.get("target_metadata"),
        "ast_evidence": result.get("ast_evidence"),
    }
    if result.get("edit_kind") == "unified_diff":
        payload["unified_diff"] = result.get("unified_diff")
    if result.get("edit_kind") == "structured_edit":
        payload["structured_operations"] = result.get("structured_operations")
    return _agentic_v9_clean(payload)


def _agentic_v9_render_code_edit_proposal_call(call):
    result = _agentic_v9_as_dict(call.get("result"))
    payload = _agentic_v9_code_edit_proposal_payload(result)
    lines = [f"### TOOL RIUSCITO: {_agentic_v9_tool_block_header(call)}"]
    if not payload:
        lines.append("- code_edit_proposal mancante nel payload inline.")
        return lines
    for key, value in payload.items():
        if key == "unified_diff" and isinstance(value, str):
            lines.extend(["unified_diff:", "````diff", value, "````"])
        elif key == "structured_operations":
            lines.extend(["structured_operations:", "````json", _agentic_v9_json.dumps(value, ensure_ascii=False, indent=2, default=str), "````"])
        elif isinstance(value, str) and "\n" in value:
            lines.extend([f"{key}:", "````text", value, "````"])
        else:
            lines.append(f"{key}: {_agentic_v9_line_value(value)}")
    return lines


def _agentic_v9_render_generic_tool_call(call):
    result = _agentic_v9_as_dict(call.get("result"))
    payload = _agentic_v9_generic_tool_payload(result)
    lines = [f"### TOOL RIUSCITO: {_agentic_v9_tool_block_header(call)}"]
    if not payload:
        lines.append("- risultato riuscito presente ma senza campi utili inline.")
        return lines
    for key, value in payload.items():
        if isinstance(value, str) and "\n" in value:
            lines.extend([f"{key}:", "````text", value, "````"])
        else:
            lines.append(f"{key}: {_agentic_v9_line_value(value)}")
    return lines


def _agentic_v9_append_successful_tool_evidence(lines, observation):
    calls = _agentic_v9_successful_calls(observation)
    lines.append("EVIDENZA INLINE DEI TOOL RIUSCITI:")
    if not calls:
        lines.append("- nessuna evidenza tool riuscita disponibile nel payload.")
        return
    for call in calls:
        tool = str(call.get("tool_name") or "")
        lines.append("")
        if tool in {"repo_tree", "repo_tree_files", "tree"}:
            lines.extend(_agentic_v9_render_repo_tree_call(call))
        elif tool in {"repo_list_files", "repo_file_list", "list_files"}:
            lines.extend(_agentic_v9_render_repo_list_files_call(call))
        elif tool in {"repo_read", "repo_file_read", "read_file"}:
            lines.extend(_agentic_v9_render_repo_read_call(call))
        elif tool in {"repo_propose_code_edit", "code_edit_proposal"}:
            lines.extend(_agentic_v9_render_code_edit_proposal_call(call))
        else:
            lines.extend(_agentic_v9_render_generic_tool_call(call))


def _agentic_v9_successful_tool_limits(observation):
    limits = []
    for call in _agentic_v9_successful_calls(observation):
        tool = str(call.get("tool_name") or "")
        result = _agentic_v9_as_dict(call.get("result"))
        step = call.get("step")
        if result.get("truncated") is True:
            limits.append(f"- step={step} tool={tool} truncated=true path={result.get('path') or ''}".rstrip())
        if tool in {"repo_list_files", "repo_file_list", "list_files"}:
            total = result.get("total_matches") or result.get("paths_total") or result.get("files_total")
            visible = len(_agentic_v9_as_list(result.get("paths") or result.get("paths_preview") or result.get("files") or result.get("files_preview")))
            if total not in (None, "") and visible and int(total) > visible:
                limits.append(f"- step={step} tool={tool} lista parziale: visible={visible} total={total}")
        if tool in {"repo_read", "repo_file_read", "read_file"}:
            raw_items = _agentic_v9_as_list(result.get("items")) or ([result] if result.get("path") else [])
            for item in raw_items:
                item = _agentic_v9_as_dict(item)
                if item.get("ok") is False:
                    continue
                content, source, preview_only = _agentic_v9_read_item_content(item)
                if item.get("truncated") is True:
                    limits.append(f"- step={step} tool={tool} repo_read truncated=true path={item.get('path')}")
                if preview_only:
                    limits.append(f"- step={step} tool={tool} repo_read preview_only=true path={item.get('path')} source={source}")
                if not content:
                    limits.append(f"- step={step} tool={tool} repo_read content_missing path={item.get('path')}")
    return _agentic_v9_unique_texts(limits)


def _agentic_v9_structured_repo_tree_result(result):
    result = _agentic_v9_as_dict(result)
    entries = _agentic_v9_as_list(result.get("entries") or result.get("entries_preview"))
    out = {
        "ok": result.get("ok"),
        "path": _agentic_v9_repo_result_path(result),
        "count": result.get("count"),
        "entries_total": result.get("entries_total") or result.get("count") or len(entries),
        "truncated": result.get("truncated"),
        "entries": entries,
    }
    return _agentic_v9_clean(out)


def _agentic_v9_structured_repo_list_files_result(result):
    result = _agentic_v9_as_dict(result)
    paths = _agentic_v9_as_list(result.get("paths") or result.get("paths_preview"))
    files = _agentic_v9_as_list(result.get("files") or result.get("files_preview"))
    out = {
        "ok": result.get("ok"),
        "path": _agentic_v9_repo_result_path(result),
        "count": result.get("count") or result.get("paths_total") or result.get("files_total") or len(paths) or len(files),
        "total_matches": result.get("total_matches") or result.get("paths_total") or result.get("files_total") or len(paths) or len(files),
        "paths_total": result.get("paths_total"),
        "files_total": result.get("files_total"),
        "limit": result.get("limit"),
        "truncated": result.get("truncated"),
        "paths": paths,
    }
    if files and not paths:
        out["files"] = files
    return _agentic_v9_clean(out)


def _agentic_v9_structured_repo_read_result(result):
    result = _agentic_v9_as_dict(result)
    raw_items = _agentic_v9_as_list(result.get("items"))
    if not raw_items and _agentic_v9_repo_result_path(result):
        raw_items = [result]
    items = []
    for item in raw_items:
        item = _agentic_v9_as_dict(item)
        if not item or item.get("ok") is False:
            continue
        content, source, preview_only = _agentic_v9_read_item_content(item)
        row = {
            "ok": item.get("ok", True),
            "path": _agentic_v9_repo_result_path(item),
            "line_count": item.get("line_count"),
            "truncated": item.get("truncated"),
            "preview_only": preview_only,
        }
        if source == "content":
            row["content"] = content
        elif source == "content_preview":
            row["content_preview"] = content
        items.append(_agentic_v9_clean(row))
    return _agentic_v9_clean({
        "ok": result.get("ok"),
        "count": result.get("count") or len(items),
        "items": items,
    })


def _agentic_v9_structured_tool_result(tool, result):
    if tool in {"repo_tree", "repo_tree_files", "tree"}:
        return _agentic_v9_structured_repo_tree_result(result)
    if tool in {"repo_list_files", "repo_file_list", "list_files"}:
        return _agentic_v9_structured_repo_list_files_result(result)
    if tool in {"repo_read", "repo_file_read", "read_file"}:
        return _agentic_v9_structured_repo_read_result(result)
    if tool in {"repo_propose_code_edit", "code_edit_proposal"}:
        return _agentic_v9_code_edit_proposal_payload(result)
    return _agentic_v9_clean(_agentic_v9_generic_tool_payload(result))


def _agentic_v9_merge_loaded_artifact(value):
    value = _agentic_v9_as_dict(value)
    artifact_path = _agentic_v9_artifact_path(value, value)
    if not artifact_path:
        return value
    loaded, _load_meta = _agentic_v9_read_json_artifact(artifact_path)
    if isinstance(loaded, dict):
        return {**value, **loaded}
    return value


def _agentic_v9_repo_tree_artifact(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    structured = _agentic_v9_structured_repo_tree_result(result)
    artifact = {
        "kind": "repo_tree",
        "repo_path": structured.get("path") or args.get("path") or ".",
        "count": structured.get("count"),
        "entries_total": structured.get("entries_total"),
        "truncated": structured.get("truncated"),
        "entries": structured.get("entries"),
    }
    return [_agentic_v9_clean({
        "producer_step": call.get("step"),
        "tool": call.get("tool_name"),
        "arguments": args,
        "ok": structured.get("ok", True),
        "artifact": artifact,
    })]


def _agentic_v9_repo_list_files_artifact(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    structured = _agentic_v9_structured_repo_list_files_result(result)
    artifact = {
        "kind": "repo_list_files",
        "repo_path": structured.get("path") or args.get("path") or ".",
        "count": structured.get("count"),
        "total_matches": structured.get("total_matches"),
        "limit": structured.get("limit"),
        "truncated": structured.get("truncated"),
        "paths": structured.get("paths") or structured.get("files"),
    }
    return [_agentic_v9_clean({
        "producer_step": call.get("step"),
        "tool": call.get("tool_name"),
        "arguments": args,
        "ok": structured.get("ok", True),
        "artifact": artifact,
    })]


def _agentic_v9_repo_read_artifacts(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    raw_items = _agentic_v9_as_list(result.get("items"))
    if not raw_items and _agentic_v9_repo_result_path(result):
        raw_items = [result]
    artifacts = []
    for raw_item in raw_items:
        item = _agentic_v9_merge_loaded_artifact(raw_item)
        if not item or item.get("ok") is False:
            continue
        content, source, preview_only = _agentic_v9_read_item_content(item)
        artifact = {
            "kind": "repo_read",
            "repo_path": _agentic_v9_repo_result_path(item),
            "line_count": item.get("line_count"),
            "truncated": item.get("truncated"),
            "preview_only": preview_only,
        }
        if source == "content":
            artifact["content"] = content
        elif source == "content_preview":
            artifact["content_preview"] = content
        artifacts.append(_agentic_v9_clean({
            "producer_step": call.get("step"),
            "tool": call.get("tool_name"),
            "arguments": args,
            "ok": item.get("ok", True),
            "artifact": artifact,
        }))
    return artifacts


def _agentic_v9_generic_tool_artifact(call):
    result = _agentic_v9_as_dict(call.get("result"))
    args = _agentic_v9_as_dict(call.get("arguments"))
    payload = _agentic_v9_generic_tool_payload(result)
    tool = str(call.get("tool_name") or "")
    kind = "command_result" if tool in {"repo_command", "terminal_run_command_wait"} else "tool_result"
    artifact = {"kind": kind, **_agentic_v9_as_dict(payload)}
    return [_agentic_v9_clean({
        "producer_step": call.get("step"),
        "tool": tool,
        "arguments": args,
        "ok": result.get("ok", True),
        "artifact": _agentic_v9_artifact_content_last(artifact),
    })]


def _agentic_v9_code_edit_proposal_artifact(call):
    result = _agentic_v9_merge_loaded_artifact(_agentic_v9_as_dict(call.get("result")))
    args = _agentic_v9_as_dict(call.get("arguments"))
    artifact = _agentic_v9_code_edit_proposal_payload(result)
    artifact = {"kind": "code_edit_proposal", **_agentic_v9_as_dict(artifact)}
    return [_agentic_v9_clean({
        "producer_step": call.get("step"),
        "tool": call.get("tool_name"),
        "arguments": args,
        "ok": result.get("ok", True),
        "artifact": _agentic_v9_artifact_content_last(artifact),
    })]


def _agentic_v9_artifact_content_last(artifact):
    artifact = _agentic_v9_as_dict(artifact)
    if not artifact:
        return artifact
    out = {}
    delayed = {}
    for key, value in artifact.items():
        if key in {"content", "content_preview", "stdout", "stderr", "stdout_tail", "stderr_tail", "unified_diff"}:
            delayed[key] = value
        else:
            out[key] = value
    out.update(delayed)
    return out


def _agentic_v9_artifact_has_text_payload(row):
    artifact = _agentic_v9_as_dict(_agentic_v9_as_dict(row).get("artifact"))
    for key in ("content", "content_preview", "stdout", "stderr", "stdout_tail", "stderr_tail", "unified_diff"):
        if artifact.get(key) not in (None, "", [], {}):
            return True
    return False


def _agentic_v9_order_artifacts(artifacts):
    light = []
    text_heavy = []
    for row in _agentic_v9_as_list(artifacts):
        row = _agentic_v9_as_dict(row)
        if isinstance(row.get("artifact"), dict):
            row = {**row, "artifact": _agentic_v9_artifact_content_last(row.get("artifact"))}
        if _agentic_v9_artifact_has_text_payload(row):
            text_heavy.append(row)
        else:
            light.append(row)
    return light + text_heavy


def _agentic_v9_tool_artifacts(call):
    tool = str(call.get("tool_name") or "")
    if tool in {"repo_tree", "repo_tree_files", "tree"}:
        return _agentic_v9_repo_tree_artifact(call)
    if tool in {"repo_list_files", "repo_file_list", "list_files"}:
        return _agentic_v9_repo_list_files_artifact(call)
    if tool in {"repo_read", "repo_file_read", "read_file"}:
        return _agentic_v9_repo_read_artifacts(call)
    if tool in {"repo_propose_code_edit", "code_edit_proposal"}:
        return _agentic_v9_code_edit_proposal_artifact(call)
    return _agentic_v9_generic_tool_artifact(call)


def _agentic_v9_structured_tool_limits(observation):
    limits = []
    for call in _agentic_v9_successful_calls(observation):
        tool = str(call.get("tool_name") or "")
        result = _agentic_v9_as_dict(call.get("result"))
        step = call.get("step")
        path = _agentic_v9_repo_result_path(result)
        if result.get("truncated") is True:
            limits.append(_agentic_v9_clean({
                "step": step,
                "tool": tool,
                "kind": "truncated",
                "path": path,
            }))
        if tool in {"repo_list_files", "repo_file_list", "list_files"}:
            total = result.get("total_matches") or result.get("paths_total") or result.get("files_total")
            visible = len(_agentic_v9_as_list(result.get("paths") or result.get("paths_preview") or result.get("files") or result.get("files_preview")))
            if total not in (None, "") and visible and int(total) > visible:
                limits.append(_agentic_v9_clean({
                    "step": step,
                    "tool": tool,
                    "kind": "partial_list",
                    "path": path,
                    "visible": visible,
                    "total": total,
                }))
        if tool in {"repo_read", "repo_file_read", "read_file"}:
            raw_items = _agentic_v9_as_list(result.get("items")) or ([result] if _agentic_v9_repo_result_path(result) else [])
            for item in raw_items:
                item = _agentic_v9_as_dict(item)
                if item.get("ok") is False:
                    continue
                content, source, preview_only = _agentic_v9_read_item_content(item)
                if item.get("truncated") is True:
                    limits.append(_agentic_v9_clean({
                        "step": step,
                        "tool": tool,
                        "kind": "truncated_read",
                        "path": _agentic_v9_repo_result_path(item),
                    }))
                if preview_only:
                    limits.append(_agentic_v9_clean({
                        "step": step,
                        "tool": tool,
                        "kind": "preview_only_read",
                        "path": _agentic_v9_repo_result_path(item),
                        "source": source,
                    }))
                if not content:
                    limits.append(_agentic_v9_clean({
                        "step": step,
                        "tool": tool,
                        "kind": "missing_read_content",
                        "path": _agentic_v9_repo_result_path(item),
                    }))
    return limits


def _agentic_v9_priority_item_from_artifact(row):
    row = _agentic_v9_as_dict(row)
    artifact = _agentic_v9_as_dict(row.get("artifact"))
    kind = str(artifact.get("kind") or "")
    tool = row.get("tool")
    step = row.get("producer_step")
    if kind == "code_edit_proposal":
        edit_kind = artifact.get("edit_kind")
        item = {
            "kind": "code_edit_proposal",
            "tool": tool,
            "step": step,
            "ok": row.get("ok", True),
            "target_file": artifact.get("target_file"),
            "edit_kind": edit_kind,
            "payload_is_complete": False,
            "source_writes_performed": artifact.get("source_writes_performed"),
            "patch_application_performed": artifact.get("patch_application_performed"),
            "manual_review_required": artifact.get("manual_review_required"),
            "rationale": artifact.get("rationale"),
            "validation_commands": artifact.get("validation_commands"),
            "warnings": artifact.get("warnings"),
            "errors": artifact.get("errors"),
            "target_metadata": artifact.get("target_metadata"),
            "ast_evidence": artifact.get("ast_evidence"),
        }
        if edit_kind == "unified_diff":
            diff = artifact.get("unified_diff")
            item["payload_is_complete"] = isinstance(diff, str) and bool(diff.strip())
            item["unified_diff"] = diff
        elif edit_kind == "structured_edit":
            operations = artifact.get("structured_operations")
            item["payload_is_complete"] = bool(operations)
            item["structured_operations"] = operations
        elif edit_kind == "no_op":
            rationale = artifact.get("rationale")
            item["payload_is_complete"] = isinstance(rationale, str) and bool(rationale.strip())
        return _agentic_v9_clean(item)
    if kind == "repo_read":
        content = artifact.get("content")
        if not isinstance(content, str) or not content:
            return {}
        if artifact.get("truncated") is True or artifact.get("preview_only") is True:
            return {}
        return _agentic_v9_clean({
            "kind": "repo_file_full_content",
            "tool": tool,
            "step": step,
            "ok": row.get("ok", True),
            "path": artifact.get("repo_path"),
            "payload_is_complete": True,
            "chars": len(content),
            "line_count": artifact.get("line_count"),
            "content": content,
        })
    return {}


def _agentic_v9_repo_analysis_priority_item(tool_context, planner_text):
    evidence_files = []
    for row in _agentic_v9_as_list(_agentic_v9_as_dict(tool_context).get("artifacts")):
        row = _agentic_v9_as_dict(row)
        artifact = _agentic_v9_as_dict(row.get("artifact"))
        kind = str(artifact.get("kind") or "")
        path = artifact.get("repo_path")
        if not path and isinstance(row.get("arguments"), dict):
            path = row["arguments"].get("path")
        if kind not in {"repo_read", "repo_tree", "repo_list_files"} and not path:
            continue
        evidence_files.append(_agentic_v9_clean({
            "step": row.get("producer_step"),
            "tool": row.get("tool"),
            "kind": kind or "tool_evidence",
            "path": path,
            "truncated": artifact.get("truncated"),
            "preview_only": artifact.get("preview_only"),
            "reason": "successful_tool_evidence_available_in_tool_context_for_30b",
        }))
    if not planner_text and not evidence_files:
        return {}
    return _agentic_v9_clean({
        "kind": "repo_analysis_summary",
        "payload_is_complete": bool(planner_text),
        "summary": planner_text,
        "evidence_files": evidence_files[:80],
    })


def _agentic_v9_build_priority_evidence_for_30b(tool_context, planner_text, *, completed=True):
    tool_context = _agentic_v9_as_dict(tool_context)
    artifact_items = []
    for row in _agentic_v9_as_list(tool_context.get("artifacts")):
        item = _agentic_v9_priority_item_from_artifact(row)
        if item:
            artifact_items.append(item)
    partial_items = []
    for row in _agentic_v9_as_list(tool_context.get("partial_products_for_30b")):
        item = _agentic_v9_as_dict(row)
        if item:
            item = dict(item)
            item.setdefault("payload_is_complete", False)
            item.setdefault("validator_accepted", False)
            partial_items.append(_agentic_v9_clean(item))
    analysis_item = _agentic_v9_repo_analysis_priority_item(tool_context, planner_text)
    priority_items = []
    if not completed:
        priority_items.extend(partial_items)
        priority_items.extend(artifact_items)
        if analysis_item:
            priority_items.append(analysis_item)
    else:
        priority_items.extend(artifact_items)
        priority_items.extend(partial_items)
        if analysis_item:
            priority_items.append(analysis_item)
    if completed and analysis_item and analysis_item not in priority_items:
        priority_items.append(analysis_item)
    return _agentic_v9_clean({
        "schema": "openwebui.priority_evidence_for_30b.v1",
            "High-priority evidence for the 30B model. Complete payloads here "
            "are real inline payloads selected from successful tool artifacts. "
            "Partial products are explicitly marked validator_accepted=false and "
            "must not be treated as completed diffs."
            "Read priority_evidence_for_30b.items before opening the artifact "
            "mirror in tool_context_for_30b.artifacts[*].artifact. When the internal job did not complete, useful status or "
            "partial products are intentionally first; do not stop at the "
            "terminal warning."
        
        "items": priority_items,
        "limits": tool_context.get("limits"),
    })


def _agentic_v9_payload_index_context_location(tool_context, item):
    tool_context = _agentic_v9_as_dict(tool_context)
    item = _agentic_v9_as_dict(item)
    kind = str(item.get("kind") or "")
    target_file = str(item.get("target_file") or "")
    path = str(item.get("path") or "")
    for index, row in enumerate(_agentic_v9_as_list(tool_context.get("artifacts"))):
        artifact = _agentic_v9_as_dict(_agentic_v9_as_dict(row).get("artifact"))
        artifact_kind = str(artifact.get("kind") or "")
        if kind == "code_edit_proposal" and artifact_kind == "code_edit_proposal":
            if target_file and str(artifact.get("target_file") or "") != target_file:
                continue
            edit_kind = str(artifact.get("edit_kind") or "")
            if edit_kind == "unified_diff":
                return f"tool_context_for_30b.artifacts[{index}].artifact.unified_diff"
            if edit_kind == "structured_edit":
                return f"tool_context_for_30b.artifacts[{index}].artifact.structured_operations"
            return f"tool_context_for_30b.artifacts[{index}].artifact"
        if kind == "repo_file_full_content" and artifact_kind == "repo_read":
            if path and str(artifact.get("repo_path") or "") != path:
                continue
            return f"tool_context_for_30b.artifacts[{index}].artifact.content"
    return "tool_context_for_30b.artifacts[*].artifact"


def _agentic_v9_payload_index_item_location(item, index, tool_context):
    item = _agentic_v9_as_dict(item)
    kind = str(item.get("kind") or "")
    base = f"priority_evidence_for_30b.items[{index}]"
    if kind == "code_edit_proposal":
        edit_kind = str(item.get("edit_kind") or "")
        if edit_kind == "unified_diff":
            field = "unified_diff"
            payload_type = "unified_diff"
        elif edit_kind == "structured_edit":
            field = "structured_operations"
            payload_type = "structured_operations"
        else:
            field = "rationale"
            payload_type = "code_edit_proposal"
        return _agentic_v9_clean({
            "kind": "code_edit_proposal",
            "payload_type": payload_type,
            "target_file": item.get("target_file"),
            "edit_kind": edit_kind,
            "payload_is_complete": item.get("payload_is_complete"),
            "primary_location": f"{base}.{field}",
        })
    if kind == "repo_file_full_content":
        return _agentic_v9_clean({
            "kind": "repo_file_full_content",
            "payload_type": "file_content",
            "path": item.get("path"),
            "payload_is_complete": item.get("payload_is_complete"),
            "primary_location": f"{base}.content",
        })
    if kind in {"partial_code_product_candidate", "partial_code_product_build_state", "action_plan_candidate", "repair_candidate_text"}:
        if item.get("unified_diff"):
            field = "unified_diff"
            payload_type = "partial_unified_diff"
        elif item.get("structured_operations"):
            field = "structured_operations"
            payload_type = "partial_structured_operations"
        elif item.get("old_text") is not None or item.get("new_text") is not None:
            field = "old_text_new_text"
            payload_type = "partial_old_text_new_text"
        elif item.get("state_text"):
            field = "state_text"
            payload_type = "partial_code_product_state"
        else:
            field = "text"
            payload_type = "partial_text"
        primary_location = f"{base}.{field}"
        if field == "old_text_new_text":
            primary_location = {
                "old_text": f"{base}.old_text",
                "new_text": f"{base}.new_text",
            }
        return _agentic_v9_clean({
            "kind": kind,
            "payload_type": payload_type,
            "target_file": item.get("target_file"),
            "edit_kind": item.get("edit_kind"),
            "payload_is_complete": item.get("payload_is_complete", False),
            "validator_accepted": item.get("validator_accepted", False),
            "primary_location": primary_location,
        })
    return {}


def _agentic_v9_partial_products_from_decoded(decoded):
    context_key, context = _agentic_v9_extract_context(decoded)
    result = _agentic_v9_extract_result(decoded, context)
    out = []
    seen = set()
    for source in (context, result, decoded):
        source = _agentic_v9_as_dict(source)
        rows = _agentic_v9_as_list(source.get("partial_products_for_30b"))
        best = source.get("best_partial_product_for_30b") if isinstance(source.get("best_partial_product_for_30b"), dict) else {}
        for row in ([best] if best else []) + rows:
            item = _agentic_v9_as_dict(row)
            if not item:
                continue
            key = _agentic_v9_json_dumps(item, indent=None)[:12000]
            if key in seen:
                continue
            seen.add(key)
            out.append(_agentic_v9_clean(item))
    for item in _agentic_v9_partial_products_from_history(_agentic_v9_as_list(result.get("history"))):
        key = _agentic_v9_json_dumps(item, indent=None)[:12000]
        if key in seen:
            continue
        seen.add(key)
        out.append(_agentic_v9_clean(item))
    return out[:20]


def _agentic_v9_partial_products_from_history(history):
    out = []
    seen = set()

    def add(item):
        item = _agentic_v9_as_dict(item)
        if not item or len(out) >= 12:
            return
        key = _agentic_v9_json_dumps(item, indent=None)[:12000]
        if key in seen:
            return
        seen.add(key)
        out.append(_agentic_v9_clean(item))

    for row in reversed(_agentic_v9_as_list(history)):
        row = _agentic_v9_as_dict(row)
        step = row.get("step")
        result = _agentic_v9_as_dict(row.get("tool_result"))
        rejected = _agentic_v9_as_dict(result.get("rejected_decision"))
        args = _agentic_v9_as_dict(rejected.get("arguments"))
        tool = str(rejected.get("tool") or "")
        summary = str(result.get("summary") or "")
        violations = _agentic_v9_as_list(result.get("violations"))
        if tool == "repo_propose_code_edit":
            add({
                "kind": "partial_code_product_candidate",
                "source": "validator_rejected_repo_propose_code_edit",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": args.get("target_file"),
                "edit_kind": args.get("edit_kind"),
                "rationale": args.get("rationale"),
                "unified_diff": args.get("unified_diff"),
                "old_text": args.get("old_text"),
                "new_text": args.get("new_text"),
                "structured_operations": args.get("structured_operations") if isinstance(args.get("structured_operations"), list) else None,
                "reason": rejected.get("reason"),
            })
        if tool == "planner_scratchpad_write" and str(args.get("kind") or "") == "code_product_build_state":
            state_text = str(args.get("text") or args.get("content") or "").strip()
            target_file = args.get("target_file")
            status = None
            edit_kind = None
            rationale = None
            if state_text:
                parsed = _agentic_v9_parse_jsonish(state_text)
                parsed = _agentic_v9_as_dict(parsed)
                payload = _agentic_v9_as_dict(parsed.get("payload")) or parsed
                target_file = target_file or payload.get("target_file")
                status = payload.get("status")
                edit_kind = payload.get("edit_kind")
                rationale = payload.get("rationale")
            add({
                "kind": "partial_code_product_build_state",
                "source": "validator_rejected_code_product_build_state",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": target_file,
                "status": status,
                "edit_kind": edit_kind,
                "rationale": rationale,
                "state_text": state_text,
            })
        action_plan = str(result.get("action_plan_candidate") or "").strip()
        if action_plan:
            add({
                "kind": "action_plan_candidate",
                "source": "validator_rejected_final_for_code_product",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "text": action_plan,
            })
        repair = _agentic_v9_as_dict(result.get("vulkan_repair"))
        if repair:
            repaired = _agentic_v9_as_dict(repair.get("repaired_decision"))
            text = str(
                repaired.get("final_answer")
                or repair.get("raw_text_preview")
                or repair.get("raw_planner_text_preview")
                or ""
            ).strip()
            if text:
                add({
                    "kind": "repair_candidate_text",
                    "source": "vulkan_gpu0_repair_rejected_or_unvalidated",
                    "step": step,
                    "payload_is_complete": False,
                    "validator_accepted": False,
                    "rejection_summary": summary,
                    "violations": violations,
                    "text": text,
                    "repair_error": repair.get("error"),
                })
    return out


def _agentic_v9_build_structured_tool_context(decoded):
    observation = _agentic_v9_build_observation_object(decoded)
    artifacts = []
    for call in _agentic_v9_successful_calls(observation):
        artifacts.extend(_agentic_v9_tool_artifacts(call))
    artifacts = _agentic_v9_order_artifacts(artifacts)
    return _agentic_v9_clean({
        "artifacts": artifacts,
        "partial_products_for_30b": _agentic_v9_partial_products_from_decoded(decoded),
        "limits": _agentic_v9_structured_tool_limits(observation),
    })


def _agentic_v9_strip_tool_context_narrative_duplicates(tool_context):
    if not isinstance(tool_context, dict):
        return tool_context
    cleaned = dict(tool_context)
    for key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "evidence_guide_for_30b",
        "final_answer",
        "composed_answer",
    ):
        cleaned.pop(key, None)
    usage = cleaned.get("openwebui_usage") if isinstance(cleaned.get("openwebui_usage"), dict) else {}
    if usage:
        usage = dict(usage)
        usage.pop("primary_answer_field", None)
        usage["top_level_evidence_guide_field"] = "evidence_guide_for_30b"
        usage["rule"] = (
            "This tool_context_for_30b object is evidence/context only. "
            "The global evidence_guide_for_30b field sits above it. For the "
            "external 30B surface, read tool_context_for_30b.artifacts[*].artifact "
            "only after evidence_guide_for_30b, payload_index_for_30b.concrete_results "
            "and priority_evidence_for_30b."
        )
        cleaned["openwebui_usage"] = usage
    return cleaned


def _agentic_v9_strip_public_narrative_duplicates(payload):
    if not isinstance(payload, dict):
        return payload
    cleaned = dict(payload)
    for key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "text",
        "tool_observation_for_30b",
        "openwebui_tool_observation",
        "openwebui_protocol_observation",
    ):
        cleaned.pop(key, None)
    return cleaned


def _agentic_v9_build_nonterminal_tool_context(decoded, out):
    existing_context = (
        _agentic_v9_explicit_tool_context(decoded)
        or _agentic_v9_explicit_tool_context(out)
    )
    tool_context = dict(existing_context) if isinstance(existing_context, dict) else {}
    tool_context = _agentic_v9_strip_tool_context_narrative_duplicates(tool_context)
    tool_context.setdefault("type", "agentic_loop_nonterminal_structured_context")
    tool_context["top_level_evidence_guide_field"] = "evidence_guide_for_30b"
    tool_context["not_a_summary"] = True
    job_status = _agentic_v9_clean({
        "job_id": decoded.get("job_id") or out.get("job_id"),
        "status": decoded.get("status") or out.get("status"),
        "goal": decoded.get("goal") or out.get("goal"),
        "bridge_status": decoded.get("bridge_status") or out.get("bridge_status"),
        "bridge_forwarded_to_vulkan": decoded.get("bridge_forwarded_to_vulkan") or out.get("bridge_forwarded_to_vulkan"),
    })
    if job_status:
        tool_context["job_status"] = job_status
    for key in (
        "payload_index_for_30b",
        "priority_evidence_for_30b",
        "working_memory_for_30b",
        "runtime_debug_packet",
        "controller_guard",
    ):
        value = decoded.get(key)
        if value in (None, "", [], {}):
            value = out.get(key)
        if value not in (None, "", [], {}):
            tool_context[key] = value
    result_value = decoded.get("result")
    if result_value in (None, "", [], {}):
        result_value = out.get("result")
    if result_value not in (None, "", [], {}):
        result_digest = _bridge_result_digest(result_value)
        result_digest.pop("evidence_guide_for_30b", None)
        if result_digest:
            tool_context["result_digest"] = result_digest
    return _agentic_v9_public_sanitize_value(tool_context) or {}


def _agentic_v9_completed_planner_text(decoded, answer):
    observation = _agentic_v9_build_observation_object(decoded)
    body = str(
        observation.get("internal_planner_final_text")
        or answer
        or decoded.get("message_for_30b")
        or decoded.get("summary_for_30b")
        or decoded.get("final_summary")
        or ""
    ).strip()
    final_text, original_job_evidence = _agentic_v9_split_final_and_evidence(body)
    return _agentic_v9_planner_summary_from_text(final_text or body)


def _agentic_v9_old_protocol_text(value):
    text = str(value or "").lstrip()
    head = text[:3000]
    return (
        head.startswith("TOOL OBSERVATION FOR OUTER MODEL")
        or "BEGIN STRUCTURED TOOL OBSERVATION JSON" in head
        or "continuation_surface.call_protocol" in head
    )


def _agentic_v9_terminal_planner_text(decoded, answer):
    observation = _agentic_v9_build_observation_object(decoded)
    candidates = [
        decoded.get("final_summary"),
        decoded.get("summary_for_30b"),
        decoded.get("message_for_30b"),
        decoded.get("answer_for_30b"),
        observation.get("internal_planner_final_text"),
        answer,
    ]
    for value in candidates:
        text = _agentic_v9_planner_summary_from_text(str(value or "").strip())
        if text and not _agentic_v9_old_protocol_text(text):
            return text
    status = str(observation.get("status") or decoded.get("status") or "").strip()
    if status == "max_steps_reached":
        return "Max steps reached before planner produced a final answer."
    if status:
        return f"Agentic job ended with status={status}."
    return "Agentic job ended without a planner final answer."





def _agentic_v9_build_completed_content_text(planner_text, evidence_text):
    parts = [
        "GUIDA ALL'EVIDENZA INLINE DEL PAYLOAD.",
        "Il sommario seguente non sostituisce il payload: usalo per orientarti, poi rispondi leggendo payload_index_for_30b.concrete_results, quindi priority_evidence_for_30b.items[0].content quando presente, e solo dopo tool_context_for_30b.artifacts[*].artifact.",
    ]
    planner = str(planner_text or "").strip()
    evidence = str(evidence_text or "").strip()
    if planner:
        parts.extend(["", "Sommario/risposta del planner:", planner])
    if evidence:
        parts.extend(["", "Evidenza concreta disponibile inline:", evidence])
    parts.extend([
        "",
        "Regola: se l'utente chiede dettagli, descrizione completa, file o diff, non fermarti alla frase sintetica; usa i campi indicizzati del payload.",
    ])
    return "\n".join(parts).strip() + "\n"


def _agentic_v9_has_agent_result(decoded):
    if not isinstance(decoded, dict):
        return False
    if decoded.get("service") in {"vulkan_agent", "vulkan_bridge"} and (
        decoded.get("job_id")
        or decoded.get("job_url")
        or decoded.get("tool_context")
        or decoded.get("tool_context_for_30b")
        or decoded.get("result")
    ):
        return True
    for key in _agentic_v9_context_keys():
        if isinstance(decoded.get(key), dict):
            return True
    return False


def _agentic_v9_broker_materialized_public_evidence(payload):
    payload = _agentic_v9_as_dict(payload)
    report = _agentic_v9_as_dict(payload.get("materialization_report"))
    priority = _agentic_v9_as_dict(
        payload.get("priority_evidence")
        or payload.get("priority_evidence_for_30b")
    )
    payload_index = _agentic_v9_as_dict(
        payload.get("payload_index")
        or payload.get("payload_index_for_30b")
    )
    if (
        report.get("ok") is True
        and str(report.get("owner") or "") == "3572_broker"
        and priority
        and payload_index
    ):
        return {
            "report": report,
            "priority_evidence": priority,
            "payload_index": payload_index,
        }
    return {}


_AGENTIC_V9_BRIDGE_TRANSPORT_ONLY_KEYS = {
    "arguments_from",
    "arguments_from_30b",
    "bridge_agent_url",
    "bridge_alias_called",
    "bridge_contract",
    "bridge_elapsed_seconds",
    "bridge_forwarded_to_vulkan",
    "bridge_forwarding_mode",
    "bridge_public_tool",
    "bridge_received_payload_shape",
    "bridge_status",
    "bridge_v9_protocol_wrapped_as_field",
    "bridge_v9_transport_fix",
    "bridge_waited_for_agent",
    "bridge_wrapper_guard",
    "openwebui_final_handoff",
    "openwebui_final_tool_settle_applied",
    "openwebui_final_tool_settle_seconds",
    "openwebui_final_unload_planner",
    "operation_id",
    "public_payload_lint",
    "started_job",
    "wait_completed",
    "wrapper_expected_contract",
    "workspace",
}


def _agentic_v9_strip_bridge_transport_only(payload):
    if not isinstance(payload, dict):
        return payload
    return {
        key: value
        for key, value in payload.items()
        if key not in _AGENTIC_V9_BRIDGE_TRANSPORT_ONLY_KEYS
    }


def _agentic_v9_build_openwebui_response(decoded, previous=None):
    """Return a JSON object for FastAPI/OpenWebUI, never a bare string.

    Completed jobs are sealed into one successful evidence surface for the
    outer OpenWebUI model. In-flight or blocked jobs keep the older protocol
    observation path because they are not successful evidence packs.
    """
    if not isinstance(decoded, dict):
        return decoded
    if not _agentic_v9_enabled() or not _agentic_v9_has_agent_result(decoded):
        return decoded

    # Preserve the already-compacted object when available. If the wrapped
    # function returned something else, fall back to a shallow copy of decoded.
    out = dict(previous) if isinstance(previous, dict) else dict(decoded)
    observation = _agentic_v9_build_observation_object(decoded)
    status = observation.get("status") or decoded.get("status")
    completed = observation.get("status") == "completed" or observation.get("job_ok") is True
    terminal = _agentic_v9_is_terminal_status(status) or completed
    if terminal and _agentic_v9_broker_materialized_public_evidence(decoded):
        return normalize_public_payload_field_names(
            _agentic_v9_strip_bridge_transport_only(decoded)
        )

    out["bridge_v9_protocol_wrapped_as_field"] = True
    out["bridge_v9_transport_fix"] = "json_object_not_bare_string"
    out.setdefault("service", decoded.get("service") or "vulkan_bridge")
    out.setdefault("ok", decoded.get("ok", True))
    out.setdefault("job_id", decoded.get("job_id"))
    out.setdefault("status", decoded.get("status"))
    out.setdefault("goal", decoded.get("goal"))

    answer = (
        out.get("answer_for_30b")
        or decoded.get("answer_for_30b")
        or decoded.get("message_for_30b")
        or decoded.get("summary_for_30b")
        or decoded.get("final_summary")
        or ""
    )
    if terminal:
        decoded_materialized = _agentic_v9_broker_materialized_public_evidence(decoded)
        terminal_source = decoded if decoded_materialized else _agentic_v9_full_terminal_payload(decoded)
        terminal_observation = _agentic_v9_build_observation_object(terminal_source)
        terminal_completed = terminal_observation.get("status") == "completed" or terminal_observation.get("job_ok") is True
        terminal_answer = (
            terminal_source.get("answer_for_30b")
            or terminal_source.get("message_for_30b")
            or terminal_source.get("summary_for_30b")
            or terminal_source.get("final_summary")
            or answer
        )
        if terminal_completed:
            planner_text = _agentic_v9_completed_planner_text(terminal_source, terminal_answer)
        else:
            planner_text = _agentic_v9_terminal_planner_text(terminal_source, terminal_answer)
        if not planner_text:
            planner_text = "Agentic job ended without a planner final answer."
        existing_tool_context = (
            _agentic_v9_explicit_tool_context(terminal_source)
            or _agentic_v9_explicit_tool_context(decoded)
            or _agentic_v9_explicit_tool_context(out)
        )
        tool_context = dict(existing_tool_context)
        built_tool_context = _agentic_v9_build_structured_tool_context(terminal_source)
        for key, value in built_tool_context.items():
            if key not in tool_context and value not in (None, "", [], {}):
                tool_context[key] = value
        tool_context = _agentic_v9_strip_tool_context_narrative_duplicates(tool_context)
        tool_context = _agentic_v9_public_sanitize_value(tool_context) or {}
        broker_materialized = _agentic_v9_broker_materialized_public_evidence(terminal_source)
        if broker_materialized:
            priority_evidence = (
                _agentic_v9_public_sanitize_value(broker_materialized["priority_evidence"])
                or {}
            )
            payload_index = (
                _agentic_v9_public_sanitize_value(broker_materialized["payload_index"])
                or {}
            )
        else:
            priority_evidence = _agentic_v9_build_priority_evidence_for_30b(
                tool_context,
                planner_text,
                completed=terminal_completed,
            )
            payload_index = _agentic_v9_build_payload_index_for_30b(
                priority_evidence,
                tool_context,
                completed=terminal_completed,
            )
        evidence_guide = _agentic_v9_build_completed_content_text(
            planner_text,
            tool_context.get("evidence_digest_for_30b") if isinstance(tool_context, dict) else "",
        )
        safe_keys = ("ok", "service", "mode")
        sealed = {}
        for key in safe_keys:
            value = out.get(key)
            if value in (None, "", [], {}):
                value = decoded.get(key)
            if value in (None, "", [], {}):
                value = terminal_source.get(key)
            if value not in (None, "", [], {}):
                sealed[key] = value
        # The public OpenWebUI tool call succeeded when this terminal payload is
        # shaped and returned. The internal job result is exposed as diagnostic
        # payload, not as a primary top-level field that can stop OpenWebUI.
        sealed["ok"] = True
        sealed.setdefault("service", decoded.get("service") or terminal_source.get("service") or "vulkan_agent")
        sealed.setdefault("mode", decoded.get("mode") or terminal_source.get("mode") or "agent_job_final_waited_compact")
        stable_required_top_level_keys = [
            "ok",
            "service",
            "mode",
            "required_top_level_keys",
            "evidence_guide_for_30b",
            "payload_index_for_30b",
            "priority_evidence_for_30b",
            "materialization_report",
            "openwebui_usage",
            "tool_context_for_30b",
        ]
        sealed["required_top_level_keys"] = stable_required_top_level_keys
        sealed["evidence_guide_for_30b"] = evidence_guide
        sealed["payload_index_for_30b"] = payload_index
        result_value = terminal_source.get("result")
        if result_value in (None, "", [], {}):
            result_value = decoded.get("result")
        if result_value in (None, "", [], {}):
            result_value = out.get("result")
        internal_job_status = _agentic_v9_clean({
            "completed": bool(terminal_completed),
            "status": (
                terminal_observation.get("status")
                or terminal_source.get("status")
                or decoded.get("status")
                or ("completed" if terminal_completed else "not_completed")
            ),
            "payload_available": bool(priority_evidence.get("items") or tool_context or result_value not in (None, "", [], {})),
            "source": "internal_3572_job_status",
            "primary_response_status_field": "ok",
            "primary_response_status_meaning": "3571 public tool call returned a readable payload",
        })
        if isinstance(payload_index, dict):
            payload_index["internal_job_status"] = internal_job_status
        external_tool_context = _agentic_v9_build_external_tool_context_for_30b(tool_context)
        sealed["openwebui_usage"] = {
            "primary_payload_fields": [
                "evidence_guide_for_30b",
                "payload_index_for_30b.concrete_results",
                "priority_evidence_for_30b.items[0].content",
                "tool_context_for_30b.artifacts[*].artifact",
            ],
            "payload_index_field": "payload_index_for_30b",
            "evidence_guide_field": "evidence_guide_for_30b",
            "concrete_results_field": "payload_index_for_30b.concrete_results",
            "priority_evidence_field": "priority_evidence_for_30b.items",
            "full_tool_evidence_field": "tool_context_for_30b.artifacts[*].artifact",
            "top_level_present_fields": list(sealed.keys()),
            "rule": (
                "Prima leggi evidence_guide_for_30b: e' una guida corposa "
                "all'evidenza, non una frase conclusiva statica. Poi leggi "
                "payload_index_for_30b.concrete_results. Poi leggi il payload "
                "concreto indicato, per i repo_read di solito "
                "priority_evidence_for_30b.items[0].content. Solo dopo usa "
                "tool_context_for_30b.artifacts[*].artifact come mirror completo "
                "degli artifact, non come dump completo del job. "
                "I risultati concreti sono nei campi indicati in concrete_results; "
                "i risultati utili non validati sono in partial_results. "
                "Descrizioni, suggerimenti, manual_review_required, "
                "validation_commands e limits non sono motivo per richiamare "
                "vulkan_helper per la stessa richiesta."
            ),
            "internal_job_status": internal_job_status,
        }
        sealed["priority_evidence_for_30b"] = priority_evidence
        sealed["tool_context_for_30b"] = _agentic_v9_json_dumps(external_tool_context, indent=2)
        if broker_materialized:
            sealed["materialization_report"] = broker_materialized["report"]
        else:
            sealed["materialization_report"] = build_materialization_report(
                sealed,
                owner="3571_bridge",
                bridge_emergency_rehydration_used=terminal_source is not decoded,
            )
        if result_value not in (None, "", [], {}):
            sealed["result"] = _agentic_v9_public_result_for_30b(result_value)
        _attach_public_payload_lint(sealed)
        sealed["openwebui_usage"]["top_level_present_fields"] = list(sealed.keys())
        return sealed

    protocol_text = _compact_text(
        _agentic_v9_build_protocol_text(decoded),
        BRIDGE_MAX_OPENWEBUI_SUMMARY_CHARS,
    )
    out = _agentic_v9_public_sanitize_value(out) or {}
    out = _agentic_v9_strip_public_narrative_duplicates(out)
    out["evidence_guide_for_30b"] = protocol_text
    out["tool_context_for_30b"] = _agentic_v9_json_dumps(
        _agentic_v9_build_nonterminal_tool_context(decoded, out),
        indent=2,
    )
    usage = out.get("openwebui_usage") if isinstance(out.get("openwebui_usage"), dict) else {}
    usage = dict(usage)
    usage.update({
        "evidence_guide_field": "evidence_guide_for_30b",
        "structured_context_field": "tool_context_for_30b",
        "rule": (
            "Use evidence_guide_for_30b as the only top-level narrative guide. "
            "Use tool_context_for_30b for structured non-terminal job status and "
            "inline diagnostic context. Do not look for answer/message/summary/content "
            "aliases; they are intentionally not emitted."
        ),
    })
    out["openwebui_usage"] = usage

    return _attach_public_payload_lint(out)


def _compact_for_openwebui(decoded: dict[str, Any]) -> dict[str, Any]:
    previous = _legacy_compact_for_openwebui(decoded)
    if isinstance(decoded, dict):
        return normalize_public_payload_field_names(
            _agentic_v9_build_openwebui_response(decoded, previous=previous)
        )
    return normalize_public_payload_field_names(previous)


def _agentic_v2_compact_context_for_openwebui(ctx):
    context = _legacy_agentic_v2_compact_context_for_openwebui(ctx)
    if not isinstance(context, dict):
        return context
    fake = {
        "ok": True,
        "service": "vulkan_agent",
        "status": _agentic_v9_as_dict(context.get("job")).get("status"),
        "goal": _agentic_v9_as_dict(context.get("job")).get("goal"),
        "tool_context_for_30b": context,
    }
    return _agentic_v9_build_openwebui_response(fake, previous=context)

_AGENTIC_V9_OPENWEBUI_PROTOCOL_OBSERVATION_ACTIVE = True
