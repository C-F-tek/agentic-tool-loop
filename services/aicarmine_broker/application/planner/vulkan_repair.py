"""Vulkan repair, CUDA rewrite, and controller guard validation extracted from planner.py.

These functions handle Vulkan/GPU0 repair attempts, CUDA lane rewrite detection,
and controller guard result building for validation feedback.
"""
from __future__ import annotations

import json
from typing import Any


def _vulkan_repair_seen(history: list[dict[str, Any]]) -> int:
    """Count explicit Vulkan/GPU0 repair attempts already surfaced in history."""
    count = 0
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("guard_type") == "vulkan_decision_repair":
            count += 1
        elif isinstance(result.get("vulkan_repair"), dict):
            count += 1
    return count


def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
    """Extract raw planner text from a decision dict."""
    if not isinstance(decision, dict):
        return ""
    return str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )


def _list_or_empty(value: Any) -> list:
    """Return value as list or empty list."""
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict:
    """Return value as dict or empty dict."""
    return value if isinstance(value, dict) else {}


def _normalize_tool_name(value: str) -> str:
    """Normalize tool name for comparison."""
    return str(value).strip().lower()


def _prompt_clip_text(value: Any, limit: int = 12000) -> str:
    """Clip text to a character limit."""
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit]


def _evidence_contract_storage_summary(contract: dict[str, Any]) -> tuple[dict[str, Any], int, str]:
    """Return contract summary, char count, and SHA256."""
    from hashlib import sha256
    text = json.dumps(contract, ensure_ascii=False, default=str)
    chars = len(text)
    sha = sha256(text.encode("utf-8")).hexdigest()
    summary = {
        "keys": list(contract.keys())[:40],
        "char_count": chars,
    }
    return summary, chars, sha


def _controller_guard_contract_overlay(contract: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal contract overlay for the controller guard."""
    overlay: dict[str, Any] = {}
    for key in ("resolved_goal_scope", "resolved_goal_file", "goal_requests_code_product"):
        if key in contract:
            overlay[key] = contract[key]
    return overlay


def _compact_vulkan_repair_evidence_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Compact evidence contract for Vulkan repair payload."""
    compact: dict[str, Any] = {}
    for key in (
        "semantic_goal_classification",
        "goal_requests_code_product",
        "goal_requires_code_product_report",
        "goal_requests_apply",
        "action_plan_candidate",
        "target_kind",
        "resolved_goal_file",
        "resolved_goal_scope",
        "successful_repo_read_count",
        "verified_content_read_count",
        "coverage_satisfied",
        "covered_owner_paths",
        "missing_owner_paths",
        "planner_may_choose_final",
        "required_next_progress",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    return compact


def _compact_repair_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact history tail for Vulkan repair payload."""
    return [item for item in (history[-10:] if isinstance(history, list) else [])]


def role_guidance_for_goal(role: str, goal: str) -> str:
    """Return role guidance text based on goal classification."""
    return f"Role: {role}. Goal context: {goal[:200]}"


def build_runtime_debug_packet(
    *,
    job_id: str = "",
    step: int = 0,
    phase: str = "",
    goal: str = "",
    decision: dict[str, Any] | None = None,
    validator_result: dict[str, Any] | None = None,
    evidence_contract: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a runtime debug packet for controller guard events."""
    return {
        "schema": "runtime_debug_packet.v1",
        "job_id": job_id,
        "step": step,
        "phase": phase,
        "goal": goal[:500],
        "decision_preview": {k: str(v)[:200] for k, v in ((decision or {}).items())} if isinstance(decision, dict) else {},
        "validator_result_preview": {k: str(v)[:200] for k, v in ((validator_result or {}).items())} if isinstance(validator_result, dict) else {},
        "evidence_contract_summary": {
            "keys": list((evidence_contract or {}).keys())[:30]
        } if evidence_contract else {},
        "extra": extra or {},
    }


# CUDA rewrite constants and functions
_PLANNER_CUDA_REWRITE_EXACT_VIOLATIONS = {
    "repo_apply_patch_missing_path_or_paths",
    "repo_apply_patch_old_text_not_from_verified_read",
    "repo_apply_patch_placeholder_text",
    "repo_propose_code_edit_invalid_edit_kind",
    "repo_propose_code_edit_missing_rationale",
    "repo_propose_code_edit_missing_structured_operations",
    "repo_propose_code_edit_missing_unified_diff",
    "repo_propose_code_edit_no_op_has_patch_payload",
    "repo_propose_code_edit_old_text_not_from_verified_read",
    "repo_propose_code_edit_placeholder_text",
    "code_product_target_not_read",
    "final_action_plan_without_code_product",
    "final_empty_answer",
    "invalid_code_product_candidate",
    "missing_code_product_candidate",
    "planner_final_required_empty_output",
}

_PLANNER_CUDA_REWRITE_PATCH_PREFIXES = (
    "repo_apply_patch_",
    "repo_propose_code_edit_",
    "code_product_",
)

_PLANNER_CUDA_REWRITE_FINAL_PREFIXES = (
    "final_not_allowed_by_evidence_contract:",
    "final_without_",
    "repo_analysis_final_",
)


def _planner_cuda_rewrite_violations(validation: dict[str, Any]) -> list[str]:
    """Extract violation strings from validation result."""
    return [str(violation) for violation in _list_or_empty(validation.get("violations"))]


def _planner_cuda_rewrite_violation_matches(
    violations: list[str],
    *,
    exact: set[str],
    prefixes: tuple[str, ...],
) -> bool:
    """Check if violations match exact set or start with any prefix."""
    return any(violation in exact or violation.startswith(prefixes) for violation in violations)


def planner_cuda_rewrite_target(validation: dict[str, Any], decision: dict[str, Any]) -> str:
    """Determine the CUDA rewrite target (tool name or 'final')."""
    violations = _planner_cuda_rewrite_violations(validation)
    if not violations or "planner_repeated_invalid_code_product_decision" in violations:
        return ""
    action = str(decision.get("action") or "").strip().lower()
    tool = _normalize_tool_name(str(decision.get("tool") or ""))
    if (
        action == "tool"
        and tool in {"repo_apply_patch", "repo_propose_code_edit"}
        and _planner_cuda_rewrite_violation_matches(
            violations,
            exact=_PLANNER_CUDA_REWRITE_EXACT_VIOLATIONS,
            prefixes=_PLANNER_CUDA_REWRITE_PATCH_PREFIXES,
        )
    ):
        return tool
    if (
        action in {"final", "done", "complete", "completed"}
        and _planner_cuda_rewrite_violation_matches(
            violations,
            exact=_PLANNER_CUDA_REWRITE_EXACT_VIOLATIONS,
            prefixes=_PLANNER_CUDA_REWRITE_FINAL_PREFIXES,
        )
    ):
        return "final"
    if (
        action in {"block", "blocked", "need_user", "needs_user"}
        and "planner_final_required_empty_output" in violations
    ):
        return "final"
    return ""


def _planner_cuda_rewrite_instruction(
    *,
    rewrite_target: str,
    existing_instruction: str,
) -> str:
    """Build CUDA rewrite instruction text."""
    common = (
        "Retry on the planner CUDA lane only; do not ask Vulkan/GPU0 to repair this semantic "
        "proposal. Return one strict JSON decision. The controller did not synthesize a patch, "
        "tool call, or final answer."
    )
    if rewrite_target in {"repo_apply_patch", "repo_propose_code_edit"}:
        target_instruction = (
            "Rewrite the rejected patch/code-product proposal from evidence_contract and "
            "candidate_next_actions. If old_text was rejected, old_text must be an exact substring "
            "from verified repo_read content for the same path; remove unrelated final prose "
            "or protocol text from old_text/new_text. If the current evidence is insufficient, "
            "choose the validator-provided read/scratchpad candidate or return a typed block."
        )
    elif rewrite_target == "final":
        target_instruction = (
            "Rewrite the final response only when the evidence_contract allows finalization. "
            "Satisfy the finalization/code-product contract, remove unrelated patch/protocol "
            "text, and if evidence is insufficient choose candidate_next_actions or return a typed block."
        )
    else:
        target_instruction = "Rewrite the rejected decision using the validator evidence, or return a typed block."
    if existing_instruction:
        return f"{common} {target_instruction} Validator next_instruction: {existing_instruction}"
    return f"{common} {target_instruction}"


def planner_cuda_rewrite_guard_for_validation(
    validation: dict[str, Any],
    decision: dict[str, Any],
    *,
    job_id: str = "",
    step: int = 0,
    goal: str = "",
) -> dict[str, Any]:
    """Build CUDA rewrite guard for validation result."""
    guard = controller_guard_result_for_validation(
        validation,
        decision,
        job_id=job_id,
        step=step,
        goal=goal,
    )
    rewrite_target = planner_cuda_rewrite_target(validation, decision)
    guard["guard_type"] = "planner_cuda_rewrite_required"
    guard["summary"] = (
        f"planner_cuda_rewrite_required:{rewrite_target}"
        if rewrite_target else "planner_cuda_rewrite_required"
    )
    guard["rewrite_lane"] = "planner_cuda"
    guard["rewrite_target"] = rewrite_target or "decision"
    guard["controller_synthesized_repair"] = False
    guard["vulkan_repair"] = {
        "attempted": False,
        "reason": "semantic_rewrite_retry_goes_back_to_planner_cuda",
    }
    guard["next_instruction"] = _prompt_clip_text(
        _planner_cuda_rewrite_instruction(
            rewrite_target=rewrite_target,
            existing_instruction=str(guard.get("next_instruction") or "").strip(),
        ),
        4000,
    )
    guard["runtime_debug_packet"] = build_runtime_debug_packet(
        job_id=job_id,
        step=step,
        phase="CONTROLLER_GUARD",
        goal=goal,
        decision=decision,
        validator_result=validation,
        evidence_contract=_dict_or_empty(validation.get("evidence_contract")),
        extra={
            "guard_type": "planner_cuda_rewrite_required",
            "rewrite_lane": "planner_cuda",
            "rewrite_target": rewrite_target or "decision",
        },
    )
    return guard


def _should_attempt_vulkan_repair(
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
) -> bool:
    """Allow explicit IA repair, but no controller fallback/normalization."""
    if _vulkan_repair_seen(history) >= 1:
        return False
    decision = decision if isinstance(decision, dict) else {}
    action = str(decision.get("action") or "").strip().lower()
    reason = str(decision.get("reason") or "")
    contract = _dict_or_empty(validation.get("evidence_contract"))
    semantic = _dict_or_empty(contract.get("semantic_goal_classification"))
    code_contract = _dict_or_empty(contract.get("code_product_contract"))
    if (
        contract.get("goal_requests_code_product")
        or contract.get("goal_requires_code_product_report")
        or bool(code_contract.get("required"))
        or bool(semantic.get("must_produce_code_product"))
    ):
        return False
    if action == "block":
        raw_planner_text = _decision_raw_planner_text(decision)
        reason_low = reason.lower()
        if raw_planner_text and (
            "invalid_planner_output_non_json" in reason_low
            or "non-json" in reason_low
            or "no_json" in reason_low
            or "degenerate" in reason_low
            or "timeout" in reason_low
            or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        ):
            return True
        return False
    if action == "tool":
        tool = _normalize_tool_name(str(decision.get("tool") or ""))
        violations = _list_or_empty(validation.get("violations"))
        if tool in {"repo_apply_patch", "repo_propose_code_edit"}:
            return False
        disallowed_prefixes = (
            "repo_propose_code_edit_",
            "code_product_",
            "missing_code_product_candidate",
            "invalid_code_product_candidate",
            "prompt_context_continuation_required",
            "prompt_context_window_",
            "planner_scratchpad_window_",
            "planner_scratchpad_read_missing_selector",
            "repo_read_window_",
            "non_existing_path:",
            "repo_read_already_successful:",
            "repo_read_path_not_from_prior_file_evidence:",
            "repo_read_path_outside_requested_scope:",
            "repo_list_files_on_file_path_use_repo_read:",
            "repo_list_files_scope_mismatch:",
            "repo_list_files_limit_mismatch:",
            "repo_list_files_suffix_not_python:",
            "repeated_repo_list_files_after_useful_file_list",
            "tool_not_in_turn_surface",
            "native_tool_not_in_turn_surface",
            "final_required_tool_call_disallowed",
        )
        if any(str(v).startswith(disallowed_prefixes) for v in violations):
            return False
        if "repeated_same_tool_arguments_without_progress" in violations:
            return False
        return True
    return False


def vulkan_repair_invalid_planner_decision(
    *,
    goal: str,
    step: int,
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Ask Vulkan/GPU0 11435 for one explicit repair of the planner emission."""
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = raw_planner_text[:64] if raw_planner_text else ""

    if _vulkan_repair_seen(history) >= 1:
        return {
            "ok": False,
            "error": "vulkan_repair_already_attempted_for_this_job",
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    # NOTE: This function requires runtime dependencies (OLLAMA_TASK_MODEL, post_json, etc.)
    # that are not available in the extracted module. It remains in planner.py
    # and is imported from there when called.
    return {
        "ok": False,
        "error": "vulkan_repair_requires_runtime_deps",
        "raw_planner_text_preview": raw_planner_text[:2000],
        "repair_cache_key": repair_key,
        "repaired_decision": None,
    }


def controller_guard_result_for_validation(
    validation: dict[str, Any],
    decision: dict[str, Any],
    *,
    job_id: str = "",
    step: int = 0,
    goal: str = "",
) -> dict[str, Any]:
    """Build controller guard result for validation feedback."""
    violations = _list_or_empty(validation.get("violations"))
    contract = _dict_or_empty(validation.get("evidence_contract"))
    required_continuation = (
        validation.get("required_prompt_context_continuation")
        if isinstance(validation.get("required_prompt_context_continuation"), dict)
        else {}
    )
    if required_continuation:
        contract = dict(contract)
        contract["required_next_tool_call"] = required_continuation.get("tool")
        validation = dict(validation)
        validation["evidence_contract"] = contract
    contract_summary, contract_chars, contract_sha256 = _evidence_contract_storage_summary(contract)
    contract_overlay = _controller_guard_contract_overlay(contract)
    guard = {
        "tool": "controller_guard",
        "ok": True,
        "kind": "validator_feedback",
        "source": "validator",
        "guard_type": "planner_decision_validation",
        "summary": (
            "planner_decision_validation_failed: " + "; ".join(str(v) for v in violations)
            if violations else "planner_decision_validation_failed"
        ),
        "violations": violations,
        "evidence_contract_summary": contract_summary,
        "evidence_contract_chars": contract_chars,
        "evidence_contract_sha256": contract_sha256,
        "rejected_decision": {
            k: _prompt_clip_text(decision.get(k), 12000)
            if k == "final_answer" else decision.get(k)
            for k in (
                "action", "tool", "arguments", "reason", "selected_by_3572",
                "coerced_by_3572", "planner_stream_meta", "final_answer",
            )
            if decision.get(k) not in (None, "", [], {})
        },
    }
    if contract_overlay:
        guard["evidence_contract_overlay"] = contract_overlay
    if validation.get("semantic_goal_classification") not in (None, "", [], {}):
        guard["semantic_goal_classification"] = validation.get("semantic_goal_classification")
    if validation.get("invalid_decision_signature") not in (None, "", [], {}):
        guard["invalid_decision_signature"] = validation.get("invalid_decision_signature")
    if validation.get("invalid_decision_repeat_count") not in (None, "", [], {}):
        guard["invalid_decision_repeat_count"] = validation.get("invalid_decision_repeat_count")
    required_next_progress = str(contract.get("required_next_progress") or "").strip()
    if required_next_progress:
        guard["next_instruction"] = required_next_progress
    required_next_tool_call = _dict_or_empty(contract.get("required_next_tool_call"))
    if required_next_tool_call:
        guard["required_next_tool_call"] = required_next_tool_call
        guard["planner_may_choose_final"] = False
    candidate_next_actions = _list_or_empty(contract.get("candidate_next_actions"))
    if candidate_next_actions:
        guard["candidate_next_actions"] = candidate_next_actions[:6]
    runtime_debug_extra: dict[str, Any] = {}
    guard["runtime_debug_packet"] = build_runtime_debug_packet(
        job_id=job_id,
        step=step,
        phase="VALIDATE_DECISION",
        goal=goal,
        decision=decision,
        validator_result=validation,
        evidence_contract=contract_summary,
        extra=runtime_debug_extra or None,
    )
    return guard


# Local aliases for backward compatibility with planner.py imports
_vulkan_repair_seen = _vulkan_repair_seen
_decision_raw_planner_text = _decision_raw_planner_text
_planner_cuda_rewrite_violations = _planner_cuda_rewrite_violations
_planner_cuda_rewrite_violation_matches = _planner_cuda_rewrite_violation_matches
_planner_cuda_rewrite_target = planner_cuda_rewrite_target
_planner_cuda_rewrite_instruction = _planner_cuda_rewrite_instruction
_planner_cuda_rewrite_guard_for_validation = planner_cuda_rewrite_guard_for_validation
_should_attempt_vulkan_repair = _should_attempt_vulkan_repair
_vulkan_repair_invalid_planner_decision = vulkan_repair_invalid_planner_decision
_controller_guard_result_for_validation = controller_guard_result_for_validation

__all__ = [
    "_vulkan_repair_seen",
    "_decision_raw_planner_text",
    "_list_or_empty",
    "_dict_or_empty",
    "_normalize_tool_name",
    "_prompt_clip_text",
    "_evidence_contract_storage_summary",
    "_controller_guard_contract_overlay",
    "_compact_vulkan_repair_evidence_contract",
    "_compact_repair_history",
    "role_guidance_for_goal",
    "build_runtime_debug_packet",
    "_planner_cuda_rewrite_violations",
    "_planner_cuda_rewrite_violation_matches",
    "planner_cuda_rewrite_target",
    "_planner_cuda_rewrite_instruction",
    "planner_cuda_rewrite_guard_for_validation",
    "_should_attempt_vulkan_repair",
    "vulkan_repair_invalid_planner_decision",
    "controller_guard_result_for_validation",
]
