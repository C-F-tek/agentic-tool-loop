"""Planner CUDA rewrite helpers extracted from planner.py.

This module owns:
- _planner_cuda_rewrite_violations
- _planner_cuda_rewrite_violation_matches
- planner_cuda_rewrite_target
- _planner_cuda_rewrite_instruction
- planner_cuda_rewrite_guard_for_validation
"""
from __future__ import annotations

from typing import Any


# CUDA rewrite exact violations and prefixes (constants from planner.py)
_PLANNER_CUDA_REWRITE_EXACT_VIOLATIONS = frozenset({
    "planner_repeated_invalid_code_product_decision",
})

_PLANNER_CUDA_REWRITE_PATCH_PREFIXES = ("planner_patch_",)
_PLANNER_CUDA_REWRITE_FINAL_PREFIXES = ("planner_final_",)


def _list_or_empty(value: Any) -> list:
    """Safely return a list or empty list."""
    if isinstance(value, list):
        return value
    return []


# ---------------------------------------------------------------------------
# CUDA rewrite violations
# ---------------------------------------------------------------------------

def _planner_cuda_rewrite_violations(validation: dict[str, Any]) -> list[str]:
    """Extract violation strings from validation."""
    return [str(violation) for violation in _list_or_empty(validation.get("violations"))]


def _planner_cuda_rewrite_violation_matches(
    violations: list[str],
    *,
    exact: frozenset[str],
    prefixes: tuple[str, ...],
) -> bool:
    """Check if violations match exact strings or prefix patterns."""
    return any(
        violation in exact or violation.startswith(prefixes)
        for violation in violations
    )


# ---------------------------------------------------------------------------
# CUDA rewrite target detection
# ---------------------------------------------------------------------------

def planner_cuda_rewrite_target(
    validation: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    """Determine the rewrite target based on validation and decision."""
    from ...tool_contract import normalize_tool_name as _normalize_tool_name
    
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


# ---------------------------------------------------------------------------
# CUDA rewrite instruction builder
# ---------------------------------------------------------------------------

def _planner_cuda_rewrite_instruction(
    *,
    rewrite_target: str,
    existing_instruction: str,
) -> str:
    """Build CUDA rewrite instruction for planner retry."""
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


# ---------------------------------------------------------------------------
# CUDA rewrite guard builder
# ---------------------------------------------------------------------------

def _prompt_clip_text(text: str, *, max_chars: int = 2000) -> str:
    """Clip text to max_chars."""
    if not isinstance(text, str):
        return ""
    return text[:max_chars]


def planner_cuda_rewrite_guard_for_validation(
    validation: dict[str, Any],
    decision: dict[str, Any],
    *,
    job_id: str = "",
    step: int = 0,
    goal: str = "",
) -> dict[str, Any]:
    """Build CUDA rewrite guard for validation feedback."""
    from .planner_decision import controller_guard_result_for_validation
    
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
            existing_instruction="",
        ),
    )
    return guard