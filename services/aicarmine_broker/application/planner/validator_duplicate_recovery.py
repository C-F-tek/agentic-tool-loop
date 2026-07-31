"""Duplicate recovery stage extracted from validator.py.

Handles duplicate repo read recovery contract logic, forbidden path tracking,
recovery count thresholds, and evidence consumption routes.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.planner.validator_pipeline import PipelineState


class StageDuplicateRecovery:
    """Detect and handle duplicate repo read recovery."""

    def run(self, state: PipelineState) -> PipelineState:
        """Run duplicate recovery stage. Returns state with updated contract/result."""
        deps = state.deps
        contract = state.contract
        history = state.history
        violations = state.violations
        tool = state.tool
        args = state.args
        action = state.action

        # Duplicate recovery only applies to repo_read actions
        if action != "tool" or tool != "repo_read":
            return state

        # Check for duplicate repo reads
        agentic_v2_successful_read_paths = deps["agentic_v2_successful_read_paths"]
        agentic_v2_decision_paths = deps["agentic_v2_decision_paths"]
        already_read = set(agentic_v2_successful_read_paths(history))
        decision_paths = agentic_v2_decision_paths(tool, args)
        repeated_reads = [p for p in decision_paths if p in already_read]

        if repeated_reads:
            violations.append("repo_read_already_successful:" + ",".join(repeated_reads[:5]))
            # Apply duplicate repo read recovery contract
            deps["_apply_duplicate_repo_read_path_recovery_contract"](
                contract,
                repeated_reads=repeated_reads,
                history=history,
            )

        return state