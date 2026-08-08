"""Lane authority types and judge decision evaluation.

This module provides the authority types and judge decision logic that determines
whether evidence is sufficient for final or if discovery should continue.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class LaneAuthority(str, Enum):
    """Authority types that determine decision behavior."""

    PROPOSAL_ONLY = "proposal_only"  # planner.primary - proposes actions
    JUDGE_ONLY = "judge_only"  # judge.final_quality - accepts/rejects final
    ADVISORY_ONLY = "advisory_only"  # preplanner, replan - advisory only
    REPAIR_ONLY = "repair_only"  # repair.vulkan_gpu0 - fixes invalid states
    BOUNDED_SELECTION = "bounded_selection"  # orientation lanes - bounded selection


class JudgeDecision(str, Enum):
    """Judge decision outcomes that control flow."""

    FINAL_ALLOWED = "final_allowed"  # Evidence sufficient → proceed to final
    CONTINUE_DISCOVERY = "continue_discovery"  # Evidence insufficient → continue with suggestions
    TERMINAL_BLOCK = "terminal_block"  # Blocked state → terminate
    REWRITE_REQUIRED = "rewrite_required"  # Needs rewrite → cuda_rewrite lane


class AIFigure(str, Enum):
    """Figure/role that the AI model takes based on context."""

    PREPLANNER = "preplanner"  # Semantic query and RAG preseed
    PLANNER = "planner"  # Primary action proposal
    JUDGE = "judge"  # Quality gate and final decision
    REPAIR = "repair"  # Vulkan JSON/state repair


def evaluate_judge_decision(
    evidence_contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> JudgeDecision:
    """Determine if evidence is sufficient for final or if discovery should continue.

    Args:
        evidence_contract: The current evidence contract with coverage, violations, etc.
        history: The planner history rows.

    Returns:
        JudgeDecision: FINAL_ALLOWED, CONTINUE_DISCOVERY, TERMINAL_BLOCK, or REWRITE_REQUIRED.
    """
    # Check terminal block conditions first
    if _is_terminal_blocked(evidence_contract):
        return JudgeDecision.TERMINAL_BLOCK

    # Check if coverage is satisfied → final allowed
    if _is_coverage_satisfied(evidence_contract):
        return JudgeDecision.FINAL_ALLOWED

    # Check if rewrite is required (cuda_rewrite lane)
    if _is_rewrite_required(evidence_contract):
        return JudgeDecision.REWRITE_REQUIRED

    # Default: continue discovery with suggestions
    return JudgeDecision.CONTINUE_DISCOVERY


def _is_terminal_blocked(contract: dict[str, Any]) -> bool:
    """Check if the job should be terminal blocked."""
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        if final_contract.get("planner_forced_terminal_block") is True:
            return True
        if final_contract.get("final_allowed") is False and final_contract.get("reason") == "cuda_rewrite_max_attempts_exceeded":
            return True

    # Check for repeated rejections
    reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
    if reject_count >= 3:
        return True

    return False


def _is_coverage_satisfied(contract: dict[str, Any]) -> bool:
    """Check if minimum read coverage is satisfied."""
    # Check direct coverage_satisfied
    if contract.get("coverage_satisfied") is True:
        return True

    # Check minimum_read_coverage
    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        if coverage.get("coverage_satisfied") is True:
            return True

    # Check finalization_contract coverage
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        final_coverage = final_contract.get("minimum_read_coverage")
        if isinstance(final_coverage, dict):
            if final_coverage.get("coverage_satisfied") is True:
                return True

    return False


def _is_rewrite_required(contract: dict[str, Any]) -> bool:
    """Check if cuda_rewrite is required (not yet ready for judge)."""
    # Check if planner_cuda_rewrite_required is set
    if contract.get("planner_cuda_rewrite_required") is True:
        return True

    # Check if there are still missing owner paths that need reading
    missing_paths = contract.get("missing_owner_paths")
    if isinstance(missing_paths, list) and len(missing_paths) > 0:
        return False  # Need to continue discovery, not rewrite

    return False


def get_judge_suggestions(
    evidence_contract: dict[str, Any],
) -> list[str]:
    """Get concrete suggestions for continued discovery when judge returns CONTINUE_DISCOVERY.

    Args:
        evidence_contract: The current evidence contract.

    Returns:
        List of concrete suggestions for the planner to pursue.
    """
    suggestions: list[str] = []

    # Check for missing owner paths
    missing_paths = evidence_contract.get("missing_owner_paths")
    if isinstance(missing_paths, list) and len(missing_paths) > 0:
        suggestions.append(
            f"Read missing owner paths: {', '.join(missing_paths[:5])}"
        )

    # Check for required next tool call
    required_call = evidence_contract.get("required_next_tool_call")
    if isinstance(required_call, dict):
        tool = required_call.get("tool", "")
        suggestions.append(f"Execute required tool: {tool}")

    # Check for candidate next actions
    candidate_actions = evidence_contract.get("candidate_next_actions")
    if isinstance(candidate_actions, list) and len(candidate_actions) > 0:
        for action in candidate_actions[:3]:
            if isinstance(action, dict):
                tool = action.get("tool", "")
                reason = action.get("reason", "")
                suggestions.append(f"Try {tool}: {reason}")

    # Check for validation rejections
    rejections = evidence_contract.get("validation_rejections_tail")
    if isinstance(rejections, list) and len(rejections) > 0:
        last_rejection = rejections[-1]
        if isinstance(last_rejection, dict):
            reason = last_rejection.get("reason", "")
            suggestions.append(f"Address rejection: {reason}")

    return suggestions


def get_figure_instruction(figure: AIFigure, context: dict[str, Any]) -> str:
    """Return appropriate system instruction for the current figure.

    Args:
        figure: The AI figure/role to take.
        context: Additional context for the instruction.

    Returns:
        System instruction string for the figure.
    """
    if figure == AIFigure.PREPLANNER:
        return (
            "You are the PREPLANNER. Your role is semantic query and RAG preseed. "
            "Analyze the goal semantically and identify the key information needs. "
            "Return a structured preplanner response with semantic_intent and ranked_paths."
        )

    if figure == AIFigure.PLANNER:
        return (
            "You are the PLANNER. Your role is primary action proposal. "
            "Based on the evidence contract and history, propose the next concrete action. "
            "Choose from: tool execution, final answer, or block. "
            "Be specific about tool names, paths, and arguments."
        )

    if figure == AIFigure.JUDGE:
        return (
            "You are the JUDGE. Your role is quality gate and final decision. "
            "Evaluate whether the evidence contract shows sufficient coverage for finalization. "
            "If coverage_satisfied=True → approve final. "
            "If coverage_satisfied=False → request continued discovery with concrete suggestions. "
            "Check: successful_repo_read_paths, missing_owner_paths, validation_rejections."
        )

    if figure == AIFigure.REPAIR:
        return (
            "You are the REPAIR specialist. Your role is fixing invalid states and JSON. "
            "When the planner produces malformed output or invalid tool calls, "
            "repair them into valid JSON/tool_call format. "
            "Do not propose new actions - only fix existing ones."
        )

    return "Unknown figure - default to planner behavior."