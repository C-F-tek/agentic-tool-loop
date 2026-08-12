#!/usr/bin/env python3
"""Shared runtime-tool guidance for local AI providers.

This module is provider-agnostic policy. GPU/Ollama, NPU/OpenVINO and any live
provider loop can import the same allowlist, examples and fallback rules while
keeping provider-specific execution details in their own adapters.

It is intentionally report-only: helpers build request payloads and guidance,
but never execute providers, apply patches, run Blender, write SQLite databases
or change Git state.
"""
from __future__ import annotations

from typing import Any

ALLOWED_RUNTIME_TOOLS = {
    "build_python_line_count_csv",
    "build_agent_memory_inventory",
    "build_agent_agnostic_tool_inventory",
    "build_agent_transient_request_context",
    "check_python_syntax",
    "check_validation_report_contract",
    "run_gpu_planner_json_contract_smoke",
    "build_code_interpreter_report",
    "runtime_sqlite_memory",
}

FORBIDDEN_RUNTIME_TOOL_ACTIONS = {
    "shell",
    "git_write",
    "git_push",
    "patch_application",
    "provider_execution",
    "blender_runtime",
    "persistent_memory_write",
    "sqlite_write_persistent",
}

TOOL_REQUEST_DECISION_GUIDE: dict[str, Any] = {
    "principle": "When repository evidence is insufficient for a valid recommendation, request allowlisted tools instead of summarizing or echoing context.",
    "must_request_tools_when": [
        "recommendations would otherwise be empty",
        "schema-valid target files cannot be selected from current evidence",
        "syntax, line-count, validation-contract, memory, or tool inventory evidence is missing",
        "the next_best_action would be collect_more_evidence, inspect validation, or inspect inventory",
    ],
    "must_not_request_tools_when": [
        "a recommendation is already ready_for_patch_plan with concrete target_files and validation_commands",
        "the missing evidence cannot be obtained by an allowlisted runtime tool",
        "the request would require shell, git write, provider execution, Blender runtime, patch application, or persistent memory writes",
    ],
    "preferred_tool_mapping": {
        "need Python file inventory or line-count ranking": "build_python_line_count_csv",
        "need available local tool inventory": "build_agent_agnostic_tool_inventory",
        "need durable memory inventory": "build_agent_memory_inventory",
        "need transient task/request context": "build_agent_transient_request_context",
        "need syntax baseline": "check_python_syntax",
        "need validation report contract check": "check_validation_report_contract",
        "need GPU planner JSON contract check": "run_gpu_planner_json_contract_smoke",
        "need code-interpreter style static report": "build_code_interpreter_report",
        "need memory status/search": "runtime_sqlite_memory",
    },
    "valid_examples": [
        {
            "id": "need_python_inventory",
            "tool": "build_python_line_count_csv",
            "reason": "Need current Python line-count inventory before choosing safe refactor targets.",
            "args": {},
        },
        {
            "id": "need_syntax_baseline",
            "tool": "check_python_syntax",
            "reason": "Need syntax baseline before producing a manual patch plan.",
            "args": {},
        },
        {
            "id": "need_operational_memory_status",
            "tool": "runtime_sqlite_memory",
            "reason": "Need operational scratch memory status before deciding whether additional local context exists.",
            "args": {"action": "status", "scope": "operational"},
        },
    ],
    "output_rule": "If recommendations is empty and evidence_ready_for_manual_patch_count is greater than zero, tool_requests should contain at least one valid request unless missing_evidence explains why no allowlisted tool can help.",
}


def sorted_allowed_runtime_tools() -> list[str]:
    """Return a stable allowlist for prompts and validators."""

    return sorted(ALLOWED_RUNTIME_TOOLS)


def build_provider_tool_guidance_payload(provider: str) -> dict[str, Any]:
    """Return guidance that can be embedded in GPU, NPU or live provider prompts."""

    return {
        "provider": provider,
        "tool_use_contract": "emit report-only runtime tool_requests; never execute tools directly",
        "available_runtime_tools": sorted_allowed_runtime_tools(),
        "forbidden_runtime_tool_actions": sorted(FORBIDDEN_RUNTIME_TOOL_ACTIONS),
        "decision_guide": TOOL_REQUEST_DECISION_GUIDE,
        "provider_notes": {
            "gpu_ollama": "Return strict JSON only; use tool_requests when recommendations would be empty.",
            "npu_openvino": "Markdown audit is allowed, but optional tool_requests must be in a fenced JSON object or a JSON object/list.",
            "live_loop": "Separate provider-emitted tool requests from deterministic fallback requests in diagnostics.",
        },
    }


def validate_runtime_tool_request_object(value: Any, index: int = 0) -> list[str]:
    """Return validation errors for a broker-compatible runtime tool request."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"tool_requests[{index}] must be an object"]
    for key in ("id", "tool", "reason", "args"):
        if key not in value:
            errors.append(f"tool_requests[{index}] missing key: {key}")
    request_id = value.get("id")
    if not isinstance(request_id, str) or not request_id.strip():
        errors.append(f"tool_requests[{index}].id must be a non-empty string")
    tool_name = value.get("tool")
    if not isinstance(tool_name, str) or not tool_name.strip():
        errors.append(f"tool_requests[{index}].tool must be a non-empty string")
    elif tool_name not in ALLOWED_RUNTIME_TOOLS:
        errors.append(f"tool_requests[{index}].tool not allowlisted: {tool_name!r}")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"tool_requests[{index}].reason must be a non-empty string")
    args = value.get("args")
    if not isinstance(args, dict):
        errors.append(f"tool_requests[{index}].args must be an object")
    return errors


def deterministic_fallback_tool_requests(reason: str, *, max_requests: int = 3) -> list[dict[str, Any]]:
    """Build safe fallback requests when a provider fails to emit live tool calls.

    These requests are deliberately marked as deterministic fallback, not provider
    output. They provide fresh evidence without pretending the model requested it.
    """

    candidates = [
        {
            "id": "fallback_python_syntax",
            "tool": "check_python_syntax",
            "reason": f"Deterministic fallback after provider emitted no valid tool_requests: {reason}.",
            "args": {},
            "source": "deterministic_fallback",
        },
        {
            "id": "fallback_validation_contract",
            "tool": "check_validation_report_contract",
            "reason": f"Deterministic fallback to refresh validation contract evidence: {reason}.",
            "args": {},
            "source": "deterministic_fallback",
        },
        {
            "id": "fallback_transient_context",
            "tool": "build_agent_transient_request_context",
            "reason": f"Deterministic fallback to refresh transient request context: {reason}.",
            "args": {},
            "source": "deterministic_fallback",
        },
        {
            "id": "fallback_gpu_contract_smoke",
            "tool": "run_gpu_planner_json_contract_smoke",
            "reason": f"Deterministic fallback to verify planner JSON/tool-request contract: {reason}.",
            "args": {},
            "source": "deterministic_fallback",
        },
    ]
    return candidates[: max(0, max_requests)]
