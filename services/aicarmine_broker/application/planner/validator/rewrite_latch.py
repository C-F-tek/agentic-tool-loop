"""
rewrite_latch.py
================
State-machine helpers for the *final_rewrite_latch* / terminal-block lane.

Valid latch states
------------------
    inactive               – no rewrite pressure active
    rewrite_required       – first final-quality rejection; retry with rewrite
    required_gap_only      – retry allowed only via a concrete evidence gap
    terminal_block_required – must emit action=block; no further final allowed

All mutating functions return the *updated* contract dict so callers can
assign the result back in a single statement (functional style).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_LATCH_STATES = frozenset(
    {"inactive", "rewrite_required", "required_gap_only", "terminal_block_required"}
)
_MAX_CUDA_REWRITE_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Pure transition
# ---------------------------------------------------------------------------

def coerce_latch_state(value: Any) -> str:
    """Normalise an arbitrary value to a valid latch state string."""
    raw = str(value or "inactive").strip().lower()
    return raw if raw in _VALID_LATCH_STATES else "inactive"


def next_latch_state(
    current: str,
    *,
    reject_count: int,
    has_gap_route: bool,
) -> str:
    """
    Compute the next latch state given the current state and context.

    Rules
    -----
    - ``terminal_block_required`` is sticky; it never regresses.
    - A second final-quality rejection (``reject_count >= 2``) forces
      ``terminal_block_required`` regardless of other factors.
    - ``required_gap_only`` stays only when there is still a runnable gap route.
    - First rejection starts ``rewrite_required``.
    """
    current = str(current or "").strip().lower()

    if current == "terminal_block_required":
        return current  # sticky

    if reject_count >= 2:
        return "terminal_block_required"

    if current == "required_gap_only":
        return "required_gap_only" if has_gap_route else "terminal_block_required"

    return "rewrite_required"


# ---------------------------------------------------------------------------
# Contract mutations
# ---------------------------------------------------------------------------

def escalate_terminal_block_state(
    contract: dict[str, Any],
    *,
    has_gap_route: bool,
) -> dict[str, Any]:
    """
    Advance the latch toward ``terminal_block_required`` after a
    final-quality rejection.  Mutates and returns *contract*.
    """
    contract = contract if isinstance(contract, dict) else {}

    # Hard ceiling on cuda-rewrite attempts
    cuda_rewrite_count = int(contract.get("planner_rewrite_stuck_count") or 0)
    if cuda_rewrite_count >= _MAX_CUDA_REWRITE_ATTEMPTS:
        return _force_terminal_block(
            contract,
            reason="cuda_rewrite_max_attempts_exceeded",
            clear_cuda_flag=True,
        )

    current_latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
    if not current_latch or current_latch not in _VALID_LATCH_STATES:
        return contract
    if contract.get("planner_cuda_rewrite_required") is not True:
        return contract
    if current_latch == "terminal_block_required":
        contract["planner_may_choose_block"] = True
        return contract

    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count

    if reject_count >= 1:
        logger.warning(
            "Terminal block risk detected: reject_count=%d. "
            "Ensure entry points are verified before finalizing.",
            reject_count,
        )

    new_latch = next_latch_state(
        current_latch, reject_count=reject_count, has_gap_route=has_gap_route
    )
    contract["final_rewrite_latch"] = new_latch
    contract["planner_may_choose_block"] = new_latch == "terminal_block_required"

    final_contract = _get_final_contract(contract)
    if new_latch == "terminal_block_required":
        final_contract.update(
            {
                "planner_may_choose_block": True,
                "final_allowed": False,
                "planner_may_choose_final": False,
                "reason": "planner_cuda_rewrite_required_repeated_retry_block_required",
            }
        )
    elif new_latch == "required_gap_only":
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_gap_only"
    else:
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_continue"
    contract["finalization_contract"] = final_contract

    return contract


def clear_terminal_block_state(contract: dict[str, Any]) -> dict[str, Any]:
    """
    Reset all rewrite/block pressure after a valid final answer is accepted.
    Mutates and returns *contract*.
    """
    contract = contract if isinstance(contract, dict) else {}

    contract["final_rewrite_latch"] = "inactive"
    contract["planner_may_choose_block"] = False
    contract["planner_may_choose_final"] = True

    # Remove every ephemeral rewrite/block key from the top-level contract
    for key in _REWRITE_BLOCK_KEYS_TOP:
        contract.pop(key, None)

    # Clean up candidate_next_actions from final-quality entries
    existing_actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    filtered = [
        item for item in existing_actions
        if not (
            isinstance(item, dict)
            and (
                str(item.get("source") or "") == "repo_analysis_final_model_quality"
                or str(item.get("action_id") or "").startswith("repo_analysis_final_quality:")
            )
        )
    ]
    if filtered:
        contract["candidate_next_actions"] = filtered
    else:
        contract.pop("candidate_next_actions", None)

    # Reset finalization_contract
    final_contract = _get_final_contract(contract)
    final_contract["final_allowed"] = True
    final_contract["planner_may_choose_final"] = True
    final_contract["planner_may_choose_block"] = False
    for key in _REWRITE_BLOCK_KEYS_FINAL:
        final_contract.pop(key, None)

    # Clear known stale reason codes
    if final_contract.get("reason") in _STALE_REASON_CODES:
        final_contract.pop("reason", None)

    contract["finalization_contract"] = final_contract
    return contract


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_final_contract(contract: dict[str, Any]) -> dict[str, Any]:
    fc = contract.get("finalization_contract")
    return fc if isinstance(fc, dict) else {}


def _force_terminal_block(
    contract: dict[str, Any],
    *,
    reason: str,
    clear_cuda_flag: bool = False,
) -> dict[str, Any]:
    if clear_cuda_flag:
        contract["planner_cuda_rewrite_required"] = False
    final_contract = _get_final_contract(contract)
    final_contract.update(
        {
            "final_allowed": False,
            "planner_may_choose_final": False,
            "planner_may_choose_block": False,
            "reason": reason,
        }
    )
    contract["finalization_contract"] = final_contract
    return contract


# ---------------------------------------------------------------------------
# Key sets (keep in one place to avoid typo drift)
# ---------------------------------------------------------------------------

_REWRITE_BLOCK_KEYS_TOP = (
    "planner_cuda_rewrite_required",
    "planner_forced_terminal_block",
    "planner_forced_terminal_block_reason",
    "planner_final_quality_terminal_block",
    "planner_final_quality_terminal_block_count",
    "planner_final_quality_terminal_block_latched",
    "planner_final_quality_latched_patch_axes",
    "planner_final_quality_latched_operator_instructions",
    "planner_final_answer_blocked_reason",
    "planner_final_quality_public_notice",
    "required_next_tool_call",
    "required_next_tool_call_validated",
    "required_next_tool_call_validation_source",
    "required_next_tool_call_invalid_tool",
    "required_next_tool_call_invalid_reason",
    "required_next_tool_call_satisfied",
    "required_next_tool_call_satisfied_reason",
    "required_next_missing_evidences",
    "required_next_output_sections",
    "invalid_required_next_missing_evidences",
    "invalid_required_next_missing_evidence_reason",
    "invalid_required_next_tool_call_paths",
    "invalid_required_next_tool_call_reason",
    "invalid_required_next_tool_call_query",
    "required_next_progress_model_stale",
    "required_next_progress_model",
    "stale_required_next_tool_calls",
    "required_next_progress",
    "required_next_tool_call_validation_error",
    "replan_specialist_route_diagnostics",
    "replan_specialist_route_audit",
    "replan_specialist_retry_audit",
    "replan_specialist_retry_replan",
)

_REWRITE_BLOCK_KEYS_FINAL = (
    "planner_forced_terminal_block",
    "planner_forced_terminal_block_reason",
    "planner_final_quality_terminal_block",
    "planner_final_quality_terminal_block_count",
    "planner_final_quality_terminal_block_latched",
    "planner_final_quality_latched_patch_axes",
    "planner_final_quality_latched_operator_instructions",
    "planner_final_answer_blocked_reason",
    "planner_final_quality_public_notice",
    "required_next_tool_call",
    "required_next_missing_evidences",
    "required_next_output_sections",
    "replan_specialist_route_diagnostics",
    "replan_specialist_route_audit",
    "replan_specialist_retry_audit",
    "replan_specialist_retry_replan",
)

_STALE_REASON_CODES = frozenset(
    {
        "repo_analysis_final_quality_no_runnable_gap_terminal_block",
        "repo_analysis_final_model_quality_rejected_no_runnable_gap",
        "planner_cuda_rewrite_required_repeated_retry_block_required",
        "planner_cuda_rewrite_required_retry_gap_only",
        "planner_cuda_rewrite_required_retry_continue",
        "required_next_tool_call_unknown_tool",
        "required_next_tool_call_not_in_current_surface",
    }
)