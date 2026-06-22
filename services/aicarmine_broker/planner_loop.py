"""
planner_loop — Extracted loop orchestration from planner.py.

Responsibilities:
- Multi-step agentic loop execution (run_agentic_planner_job)
- Loop state management
- Tool execution gating (_agentic_tool_allowed)
- Loop-level helpers and constants

This module is extracted from services/aicarmine_broker/planner.py (6064 lines).
All imports are lazy via the deps dict pattern to avoid circular imports.
"""
from __future__ import annotations

from typing import Any

from .config import (
    AGENT_DEFAULT_MAX_STEPS,
    AGENT_MAX_STEPS,
    AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
    AGENTIC_PLANNER_NATIVE_TOOLS,
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_NUM_CTX_REQUESTED,
    AGENTIC_PLANNER_NUM_PREDICT,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
    AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    AGENTIC_PLANNER_TEMPERATURE,
    AGENTIC_PLANNER_TOP_K,
    AGENTIC_PLANNER_TOP_P,
    AGENTIC_PLANNER_PRESENCE_PENALTY,
    AGENTIC_RESULT_COMPACT_CHARS,
    GLOBAL_TEMPERATURE,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    PLANNER_MODEL,
    PLANNER_URL,
    VALID_INTERNAL_TOOLS,
    AICARMINE_ORIENTATION_LANE_MODE,
    WRITE_GUARDED_TOOLS,
)

from .job_store import agent_job_root, append_agent_event, load_agent_job_state, write_agent_job_state, write_json
from .planner_core.json_io import post_json
from .tool_contract import normalize_tool_name


# ---------------------------------------------------------------------------
# Loop entry point
# ---------------------------------------------------------------------------

def run_agentic_planner_job(
    job_id: str,
    *,
    deps: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Main agentic planner loop orchestrator.

    Extracted from planner.py lines 5971-6046.
    Delegates to application/planner/loop.py run_agentic_planner_job with injected deps.
    """
    deps = deps or {}
    config = config or {}

    # Resolve dependencies from injected deps or lazy imports
    from .application.planner.lane_catalog import control_lane_event_metadata

    # Pull deps from injected dict or build from module-level functions
    loop_deps = {
        "agent_flow_diagnostics": deps.get("agent_flow_diagnostics"),
        "agentic_tool_allowed": _agentic_tool_allowed,
        "cached_tool_result": deps.get("cached_tool_result"),
        "cached_vulkan_repair_result": deps.get("cached_vulkan_repair_result"),
        "controller_file_code_product_orientation_preseed_plan": deps.get("controller_file_code_product_orientation_preseed_plan"),
        "controller_guard_rejection_signature": deps.get("controller_guard_rejection_signature"),
        "controller_guard_rejection_signature_count": deps.get("controller_guard_rejection_signature_count"),
        "controller_initial_area_list_plans": deps.get("controller_initial_area_list_plans"),
        "controller_initial_area_read_plan": deps.get("controller_initial_area_read_plan"),
        "controller_initial_doc_preseed_plan": deps.get("controller_initial_doc_preseed_plan"),
        "controller_memory_target_key": deps.get("controller_memory_target_key"),
        "controller_preplanner_rag_query_plan": deps.get("controller_preplanner_rag_query_plan"),
        "controller_preplanner_rag_preseed_plan": deps.get("controller_preplanner_rag_preseed_plan"),
        "controller_preseed_plan": deps.get("controller_preseed_plan"),
        "decision_memory_claim_text": deps.get("decision_memory_claim_text"),
        "decision_raw_planner_text": deps.get("decision_raw_planner_text"),
        "initial_orientation_surface_from_history": deps.get("initial_orientation_surface_from_history"),
        "controller_initial_orientation_candidate_pool": deps.get("controller_initial_orientation_candidate_pool"),
        "controller_orientation_model_select": deps.get("controller_orientation_model_select"),
        "orientation_shadow_effective_mode": deps.get("orientation_shadow_effective_mode"),
        "orientation_legacy_selected_candidate_ids": deps.get("orientation_legacy_selected_candidate_ids"),
        "orientation_shadow_selection_metrics": deps.get("orientation_shadow_selection_metrics"),
        "is_unrecoverable_plain_text_planner_output": deps.get("is_unrecoverable_plain_text_planner_output"),
        "native_required_repaired_tool_decision_disallowed": deps.get("native_required_repaired_tool_decision_disallowed"),
        "normalize_terminal_planner_decision": deps.get("normalize_terminal_planner_decision"),
        "planner_cuda_rewrite_guard_for_validation": deps.get("planner_cuda_rewrite_guard_for_validation"),
        "planner_cuda_rewrite_target": deps.get("planner_cuda_rewrite_target"),
        "planner_incomprehensible_retry_count": deps.get("planner_incomprehensible_retry_count"),
        "planner_memory_false_unavailable_claim": deps.get("planner_memory_false_unavailable_claim"),
        "planner_replan_specialist_for_validation": deps.get("planner_replan_specialist_for_validation"),
        "raw_planner_text_classification": deps.get("raw_planner_text_classification"),
        "should_attempt_vulkan_repair": deps.get("should_attempt_vulkan_repair"),
        "should_retry_incomprehensible_planner_output": deps.get("should_retry_incomprehensible_planner_output"),
        "specialist_route_audit": deps.get("specialist_route_audit"),
        "tool_cache_hit": deps.get("tool_cache_hit"),
        "tool_cache_key": deps.get("tool_cache_key"),
        "write_loop_turn_memory": deps.get("write_loop_turn_memory"),
        "agent_job_root": agent_job_root,
        "append_agent_event": append_agent_event,
        "compact_tool_result_for_planner": deps.get("compact_tool_result_for_planner"),
        "build_runtime_debug_packet": deps.get("build_runtime_debug_packet"),
        "controller_guard_count": deps.get("controller_guard_count"),
        "controller_guard_result_for_validation": deps.get("controller_guard_result_for_validation"),
        "finalize_agentic_job": deps.get("finalize_agentic_job"),
        "goal_has_write_intent": deps.get("goal_has_write_intent"),
        "history_has_tool": deps.get("history_has_tool"),
        "load_agent_job_state": load_agent_job_state,
        "planner_decision": deps.get("planner_decision"),
        "planner_evidence_contract": deps.get("planner_evidence_contract"),
        "planner_history_ledger": deps.get("planner_history_ledger"),
        "planner_memory_surface": deps.get("planner_memory_surface"),
        "repeated_tool_call_count": deps.get("repeated_tool_call_count"),
        "validate_planner_decision_against_evidence": deps.get("validate_planner_decision_against_evidence"),
        "vulkan_repair_invalid_planner_decision": deps.get("vulkan_repair_invalid_planner_decision"),
        "write_agent_job_state": write_agent_job_state,
        "write_json": write_json,
        "control_lane_event_metadata": control_lane_event_metadata,
    }

    loop_config = {
        "AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES": config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES),
        "AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": config.get("AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY", AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY),
        "AGENT_DEFAULT_MAX_STEPS": config.get("AGENT_DEFAULT_MAX_STEPS", AGENT_DEFAULT_MAX_STEPS),
        "AGENT_MAX_STEPS": config.get("AGENT_MAX_STEPS", AGENT_MAX_STEPS),
        "OLLAMA_TASK_MODEL": config.get("OLLAMA_TASK_MODEL", OLLAMA_TASK_MODEL),
        "OLLAMA_TASK_URL": config.get("OLLAMA_TASK_URL", OLLAMA_TASK_URL),
        "PLANNER_MODEL": config.get("PLANNER_MODEL", PLANNER_MODEL),
        "PLANNER_URL": config.get("PLANNER_URL", PLANNER_URL),
        "VALID_INTERNAL_TOOLS": config.get("VALID_INTERNAL_TOOLS", VALID_INTERNAL_TOOLS),
        "AICARMINE_ORIENTATION_LANE_MODE": config.get("AICARMINE_ORIENTATION_LANE_MODE", AICARMINE_ORIENTATION_LANE_MODE),
    }

    # Import and delegate to the extracted loop implementation
    from .application.planner.loop import run_agentic_planner_job as _inner_loop

    return _inner_loop(
        job_id,
        deps=loop_deps,
        config=loop_config,
    )


# ---------------------------------------------------------------------------
# Tool gating
# ---------------------------------------------------------------------------

def _agentic_tool_allowed(
    tool: str,
    args: dict[str, Any],
    approval_mode: str,
) -> tuple[bool, str]:
    """Check whether a tool is allowed under the current approval mode.

    Extracted from planner.py lines 6049-6064.
    """
    mode = str(approval_mode or "safe_write_lab").lower()
    readonly_modes = {"read_only", "readonly", "no_write", "dry_run"}

    # Use WRITE_GUARDED_TOOLS directly instead of hardcoded names to prevent drift
    if tool in WRITE_GUARDED_TOOLS and mode in readonly_modes:
        return False, f"{tool} blocked by read_only approval_mode"

    # repo_command has an additional safety gate beyond write-guard
    if tool == "repo_command":
        from .repo_tools import dangerous_command  # noqa: PLC0415
        if mode in readonly_modes and dangerous_command(
            str(args.get("command") or "")
        ):
            return False, "dangerous repo_command blocked by read_only approval_mode"

    return True, ""