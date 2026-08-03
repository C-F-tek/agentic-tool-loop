"""Repeated call detection stage extracted from validator.py.

Handles repeated tool call detection, duplicate window detection,
and duplicate repo read recovery logic.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.planner.validator_pipeline import PipelineState


class StageRepeatedCallDetection:
    """Detect repeated tool calls without progress."""

    def run(self, state: PipelineState) -> PipelineState:
        """Run repeated call detection stage."""
        deps = state.deps
        contract = state.contract
        history = state.history
        violations = state.violations
        tool = state.tool
        args = state.args
        action = state.action

        if action != "tool":
            return state

        repeated_tool_call_count = deps["repeated_tool_call_count"]
        count = repeated_tool_call_count(history, tool, args)

        if count >= 2:
            violations.append("repeated_same_tool_arguments_without_progress")
        elif count >= 1:
            # Check for specific repeated patterns
            if tool == "repo_list_files":
                known_paths = [
                    str(p)
                    for p in contract.get("successful_repo_read_paths") or []
                ]
                if known_paths:
                    violations.append("repeated_repo_list_files_after_useful_file_list")

            if tool == "repo_tree":
                violations.append("repeated_same_tool_arguments_without_progress")

        # Duplicate window detection
        if tool in ("repo_read", "planner_scratchpad_read"):
            window_signature = None
            if tool == "repo_read":
                window_signature = deps["repo_read_window_signature"](args)
            elif tool == "planner_scratchpad_read":
                window_signature = deps["planner_scratchpad_window_signature"](args)

            if window_signature:
                successful_sigs = deps["successful_window_signatures"](history, tool)
                if window_signature in successful_sigs:
                    violation_msg = f"{tool}_window_already_successful_without_progress"
                    violations.append(violation_msg)
                    # Apply duplicate window replan contract
                    deps["apply_duplicate_window_replan_contract"](
                        contract,
                        violation=violation_msg,
                        tool=tool,
                        args=args,
                        history=history,
                    )

        # Duplicate repo read recovery
        if tool == "repo_read":
            agentic_v2_read_has_window = deps["agentic_v2_read_has_window"]
            if not agentic_v2_read_has_window(args):
                already_read = set(deps["agentic_v2_successful_read_paths"](history))
                decision_paths = deps["agentic_v2_decision_paths"](tool, args)
                repeated_reads = [p for p in decision_paths if p in already_read]
                if repeated_reads:
                    violations.append("repo_read_already_successful:" + ",".join(repeated_reads[:5]))
                    deps["apply_duplicate_repo_read_path_recovery_contract"](
                        contract,
                        repeated_reads=repeated_reads,
                        history=history,
                    )

        return state