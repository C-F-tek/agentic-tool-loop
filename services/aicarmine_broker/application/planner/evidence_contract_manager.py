"""Evidence contract manager - centralized contract mutation logic.

This module extracts all evidence contract mutations from across 10+ files
into a single, testable class. The contract is the central data structure
that flows through the entire planner loop and controls decision behavior.

Design:
- Pure functions where possible (no state mutation)
- All mutations go through this class
- Event emission handled by caller
- State persistence handled by caller
- Only business logic lives in this class
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class EvidenceContractManager:
    """Manages evidence contract mutations across the planner system.

    This class centralizes all contract mutations that were previously
    scattered across 10+ files including:
    - builder.py (coverage calculation)
    - validator.py (cuda_rewrite, final_quality)
    - turn_surface_policy.py (surface policy)
    - candidate_actions.py (candidate gating)
    - history.py (history overlay)
    - loop.py (guard feedback)
    - final_quality.py (quality evaluation)
    - required_progress.py (progress extraction)
    - context_windows.py (context building)
    - history_messages.py (message building)
    """

    # Contract keys that are commonly mutated
    CONTRACT_KEYS = (
        "planner_cuda_rewrite_required",
        "final_rewrite_latch",
        "planner_may_choose_final",
        "planner_may_choose_block",
        "required_next_progress",
        "required_next_tool_call",
        "coverage_satisfied",
        "missing_owner_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "minimum_read_coverage",
        "finalization_contract",
        "candidate_next_actions",
    )

    def __init__(self) -> None:
        """Initialize with no dependencies (pure functions)."""
        pass

    # ==================================================================
    # CUDA Rewrite Contract Mutations
    # ==================================================================

    def set_cuda_rewrite_required(
        self,
        contract: dict[str, Any],
        required: bool,
        latch: str = "",
    ) -> dict[str, Any]:
        """Set planner_cuda_rewrite_required and optional final_rewrite_latch.

        Args:
            contract: The evidence contract dict.
            required: Whether cuda_rewrite is required.
            latch: Optional latch value (rewrite_required, terminal_block_required).

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["planner_cuda_rewrite_required"] = required

        if latch:
            contract["final_rewrite_latch"] = latch

        if required:
            final_contract = self._get_or_create_final_contract(contract)
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = "planner_cuda_rewrite_required"
            contract["finalization_contract"] = final_contract
            contract["planner_may_choose_final"] = False

        return contract

    def clear_cuda_rewrite_required(self, contract: dict[str, Any]) -> dict[str, Any]:
        """Clear planner_cuda_rewrite_required flag.

        Args:
            contract: The evidence contract dict.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["planner_cuda_rewrite_required"] = False
        return contract

    # ==================================================================
    # Final Rewrite Latch Mutations
    # ==================================================================

    def set_final_rewrite_latch(
        self,
        contract: dict[str, Any],
        latch: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Set final_rewrite_latch and update finalization_contract.

        Args:
            contract: The evidence contract dict.
            latch: Latch value (rewrite_required, terminal_block_required, inactive).
            reason: Optional reason for the latch.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["final_rewrite_latch"] = latch

        final_contract = self._get_or_create_final_contract(contract)
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False

        if reason:
            final_contract["reason"] = reason
        elif latch == "terminal_block_required":
            final_contract["planner_may_choose_block"] = True
            final_contract["reason"] = "final_rewrite_latch_terminal_block_required"
        else:
            final_contract["reason"] = "final_rewrite_latch_active"

        contract["finalization_contract"] = final_contract
        return contract

    def clear_final_rewrite_latch(self, contract: dict[str, Any]) -> dict[str, Any]:
        """Clear final_rewrite_latch.

        Args:
            contract: The evidence contract dict.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["final_rewrite_latch"] = "inactive"
        return contract

    # ==================================================================
    # Coverage Contract Mutations
    # ==================================================================

    def set_coverage_satisfied(
        self,
        contract: dict[str, Any],
        satisfied: bool,
        missing_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Set coverage_satisfied and update related fields.

        Args:
            contract: The evidence contract dict.
            satisfied: Whether coverage is satisfied.
            missing_paths: Optional list of missing owner paths.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)

        # Update minimum_read_coverage
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            coverage["coverage_satisfied"] = satisfied
            if missing_paths is not None:
                coverage["missing_owner_paths"] = missing_paths[:120]
        else:
            coverage = {
                "required": True,
                "coverage_satisfied": satisfied,
                "missing_owner_paths": missing_paths[:120] if missing_paths else [],
            }
            contract["minimum_read_coverage"] = coverage

        contract["coverage_satisfied"] = satisfied

        # Update finalization_contract
        final_contract = self._get_or_create_final_contract(contract)
        final_contract["coverage_satisfied"] = satisfied

        if not satisfied:
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false"
            )
            if missing_paths:
                final_contract["missing_owner_paths"] = missing_paths[:120]

        contract["finalization_contract"] = final_contract
        return contract

    def set_missing_owner_paths(
        self,
        contract: dict[str, Any],
        paths: list[str],
    ) -> dict[str, Any]:
        """Set missing_owner_paths in coverage and finalization_contract.

        Args:
            contract: The evidence contract dict.
            paths: List of missing owner paths.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            coverage["missing_owner_paths"] = paths[:120]
            contract["minimum_read_coverage"] = coverage

        final_contract = self._get_or_create_final_contract(contract)
        final_contract["missing_owner_paths"] = paths[:120]
        return contract

    # ==================================================================
    # Final Decision Permission Mutations
    # ==================================================================

    def set_planner_may_choose_final(
        self,
        contract: dict[str, Any],
        allowed: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        """Set planner_may_choose_final and update finalization_contract.

        Args:
            contract: The evidence contract dict.
            allowed: Whether planner may choose final.
            reason: Optional reason for the permission.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["planner_may_choose_final"] = allowed

        final_contract = self._get_or_create_final_contract(contract)
        final_contract["final_allowed"] = allowed
        final_contract["planner_may_choose_final"] = allowed

        if reason:
            final_contract["reason"] = reason

        contract["finalization_contract"] = final_contract
        return contract

    def set_planner_may_choose_block(
        self,
        contract: dict[str, Any],
        allowed: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        """Set planner_may_choose_block.

        Args:
            contract: The evidence contract dict.
            allowed: Whether planner may choose block.
            reason: Optional reason.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["planner_may_choose_block"] = allowed

        final_contract = self._get_or_create_final_contract(contract)
        final_contract["planner_may_choose_block"] = allowed

        if reason:
            final_contract["reason"] = reason

        contract["finalization_contract"] = final_contract
        return contract

    # ==================================================================
    # Required Next Progress/Tool Call Mutations
    # ==================================================================

    def set_required_next_progress(
        self,
        contract: dict[str, Any],
        progress: str,
    ) -> dict[str, Any]:
        """Set required_next_progress in contract.

        Args:
            contract: The evidence contract dict.
            progress: Progress instruction text.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["required_next_progress"] = progress[:4000]
        return contract

    def set_required_next_tool_call(
        self,
        contract: dict[str, Any],
        tool: str,
        arguments: dict[str, Any],
        reason: str = "",
    ) -> dict[str, Any]:
        """Set required_next_tool_call and update related fields.

        Args:
            contract: The evidence contract dict.
            tool: Tool name.
            arguments: Tool arguments.
            reason: Reason for the required call.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["required_next_tool_call"] = {
            "tool": tool,
            "arguments": arguments,
            "reason": reason[:900],
        }
        contract["planner_may_choose_final"] = False

        final_contract = self._get_or_create_final_contract(contract)
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = reason[:200] if reason else "required_next_tool_call_pending"
        contract["finalization_contract"] = final_contract

        return contract

    def clear_required_next_tool_call(
        self,
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Clear required_next_tool_call from contract.

        Args:
            contract: The evidence contract dict.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract.pop("required_next_tool_call", None)
        return contract

    # ==================================================================
    # Candidate Actions Mutations
    # ==================================================================

    def set_candidate_next_actions(
        self,
        contract: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Set candidate_next_actions in contract.

        Args:
            contract: The evidence contract dict.
            actions: List of candidate action dicts.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        contract["candidate_next_actions"] = actions[:15]
        return contract

    def append_candidate_next_action(
        self,
        contract: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        """Append a candidate action to existing list.

        Args:
            contract: The evidence contract dict.
            action: Action dict to append.

        Returns:
            Modified contract dict.
        """
        contract = dict(contract)
        existing = contract.get("candidate_next_actions", [])
        if not isinstance(existing, list):
            existing = []
        existing.append(action)
        contract["candidate_next_actions"] = existing[:15]
        return contract

    # ==================================================================
    # Helper Methods
    # ==================================================================

    def _get_or_create_final_contract(
        self,
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Get or create finalization_contract dict.

        Args:
            contract: The evidence contract dict.

        Returns:
            Finalization contract dict (new or existing).
        """
        final = contract.get("finalization_contract")
        if not isinstance(final, dict):
            final = {}
            contract["finalization_contract"] = final
        return final

    def get_contract_summary(
        self,
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Get a summary of key contract fields.

        Args:
            contract: The evidence contract dict.

        Returns:
            Summary dict with key contract state.
        """
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            coverage_satisfied = coverage.get("coverage_satisfied")
            missing_paths = coverage.get("missing_owner_paths", [])
        else:
            coverage_satisfied = contract.get("coverage_satisfied")
            missing_paths = contract.get("missing_owner_paths", [])

        final = contract.get("finalization_contract", {})
        if not isinstance(final, dict):
            final = {}

        return {
            "planner_may_choose_final": bool(contract.get("planner_may_choose_final")),
            "planner_may_choose_block": bool(contract.get("planner_may_choose_block")),
            "coverage_satisfied": coverage_satisfied,
            "missing_owner_paths_count": len(missing_paths) if isinstance(missing_paths, list) else 0,
            "final_allowed": bool(final.get("final_allowed")),
            "final_rewrite_latch": str(final.get("final_rewrite_latch") or "inactive"),
            "required_next_progress": str(contract.get("required_next_progress") or "")[:200],
            "candidate_actions_count": len(contract.get("candidate_next_actions") or []),
        }