"""Judge lane execution for final quality evaluation.

This module implements the judge_lane that evaluates whether evidence is sufficient
for finalization or if discovery should continue with concrete suggestions.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from .lane_authority import *

logger = logging.getLogger(__name__)


def execute_judge_lane(
    goal: str,
    history: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute the judge lane to evaluate evidence and make final decision.

    This function replaces the planner_cuda_rewrite_guard_for_validation call
    with a proper judge authority pattern. The judge evaluates the evidence_contract
    and returns a JudgeDecision (FINAL_ALLOWED, CONTINUE_DISCOVERY, TERMINAL_BLOCK,
    or REWRITE_REQUIRED).

    Args:
        goal: The user's goal text.
        history: The planner history rows.
        evidence_contract: The current evidence contract.
        deps: Dependency injections.
        config: Configuration dictionary.

    Returns:
        Dict with judge decision, rationale, and suggestions if CONTINUE_DISCOVERY.
    """
    # Step 1: Evaluate judge decision based on evidence_contract
    decision = evaluate_judge_decision(evidence_contract, history)

    # Step 2: Build response based on decision
    if decision == JudgeDecision.TERMINAL_BLOCK:
        return _build_terminal_block_response(goal, evidence_contract, history)

    if decision == JudgeDecision.FINAL_ALLOWED:
        return _build_final_allowed_response(goal, evidence_contract, history)

    if decision == JudgeDecision.REWRITE_REQUIRED:
        return _build_rewrite_required_response(goal, evidence_contract, history)

    # Default: CONTINUE_DISCOVERY
    return _build_continue_discovery_response(goal, evidence_contract, history)


def _build_terminal_block_response(
    goal: str,
    contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build response for TERMINAL_BLOCK decision."""
    reason = "Judge determined evidence is insufficient after maximum retries"
    final_contract = contract.get("finalization_contract", {})
    if isinstance(final_contract, dict):
        reason = str(final_contract.get("reason") or reason)

    return {
        "schema": "judge_lane_result.v1",
        "decision": JudgeDecision.TERMINAL_BLOCK.value,
        "rationale": f"Terminal block: {reason}",
        "suggestions": [],
        "final_allowed": False,
        "planner_may_choose_final": False,
        "planner_may_choose_block": True,
        "required_next_progress": "Job blocked by judge - insufficient evidence after maximum retries",
    }


def _build_final_allowed_response(
    goal: str,
    contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build response for FINAL_ALLOWED decision."""
    return {
        "schema": "judge_lane_result.v1",
        "decision": JudgeDecision.FINAL_ALLOWED.value,
        "rationale": "Judge determined evidence is sufficient for finalization",
        "suggestions": [],
        "final_allowed": True,
        "planner_may_choose_final": True,
        "planner_may_choose_block": False,
        "required_next_progress": "",
    }


def _build_rewrite_required_response(
    goal: str,
    contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build response for REWRITE_REQUIRED decision."""
    return {
        "schema": "judge_lane_result.v1",
        "decision": JudgeDecision.REWRITE_REQUIRED.value,
        "rationale": "Judge determined rewrite is required before final evaluation",
        "suggestions": get_judge_suggestions(contract),
        "final_allowed": False,
        "planner_may_choose_final": False,
        "planner_may_choose_block": False,
        "required_next_progress": "Rewrite required - use verified evidence to propose action",
        "planner_cuda_rewrite_required": True,
    }


def _build_continue_discovery_response(
    goal: str,
    contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build response for CONTINUE_DISCOVERY decision with concrete suggestions."""
    suggestions = get_judge_suggestions(contract)

    return {
        "schema": "judge_lane_result.v1",
        "decision": JudgeDecision.CONTINUE_DISCOVERY.value,
        "rationale": "Judge determined evidence is insufficient - continue discovery",
        "suggestions": suggestions,
        "final_allowed": False,
        "planner_may_choose_final": False,
        "planner_may_choose_block": False,
        "required_next_progress": (
            f"Continue discovery. Suggestions: {'; '.join(suggestions[:5])}"
            if suggestions
            else "Continue discovery with new evidence gathering"
        ),
    }


def prepare_judge_context(
    goal: str,
    history: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
) -> dict[str, Any]:
    """Prepare context for judge figure/system prompt.

    This function prepares the context that will be passed to the GPU1 planner
    when it takes the JUDGE figure role.

    Args:
        goal: The user's goal text.
        history: The planner history rows.
        evidence_contract: The current evidence contract.

    Returns:
        Dict with judge context including figure instruction and evaluation criteria.
    """
    suggestions = get_judge_suggestions(evidence_contract)
    coverage_satisfied = _check_coverage_satisfied(evidence_contract)
    missing_paths = evidence_contract.get("missing_owner_paths", [])

    return {
        "figure": AIFigure.JUDGE.value,
        "instruction": get_figure_instruction(AIFigure.JUDGE, {}),
        "evaluation_criteria": {
            "coverage_satisfied": coverage_satisfied,
            "missing_owner_paths": missing_paths[:12],
            "suggestion_count": len(suggestions),
            "history_length": len(history),
        },
        "decision_guidance": (
            "If coverage_satisfied=True → approve final. "
            "If coverage_satisfied=False → request continued discovery with suggestions."
        ),
    }


def _check_coverage_satisfied(contract: dict[str, Any]) -> bool:
    """Check if minimum read coverage is satisfied."""
    if contract.get("coverage_satisfied") is True:
        return True

    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        if coverage.get("coverage_satisfied") is True:
            return True

    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        final_coverage = final_contract.get("minimum_read_coverage")
        if isinstance(final_coverage, dict):
            if final_coverage.get("coverage_satisfied") is True:
                return True

