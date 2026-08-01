"""Path validation stage extracted ffrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

rom validator.py.

Handles path existence, scope, read verification, and evidence gap logic.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.planner.path_utils import (
    collect_repo_paths,
    known_contract_repo_paths,
)
from aicarmine_broker.application.planner.validator_pipeline import PipelineState


class StagePathValidation:
    """Validate path arguments against evidence and contract state."""

    def _coalesce_required_next_missing_paths(self, values: Any) -> list[str]:
        out: list[str] = []
        if not isinstance(values, (list, tuple, set)):
            return out
        for value in values:
            token = str(value).strip()
            if token and token not in out:
                out.append(token)
        return out[:12]

    def _stale_required_next_repo_read_paths(self, contract: dict[str, Any]) -> set[str]:
        paths: set[str] = set()
        for row in contract.get("stale_required_next_tool_calls") if isinstance(contract.get("stale_required_next_tool_calls"), list) else []:
            if not isinstance(row, dict):
                continue
            if str(row.get("tool") or "") != "repo_read":
                continue
            args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
            for path in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
                token = str(path).strip()
                if token:
                    paths.add(token)
        return paths

    def _successful_read_paths_for_final_route(
        self,
        contract: dict[str, Any],
        history: list[dict[str, Any]],
        agentic_v2_successful_read_paths: Any,
    ) -> set[str]:
        successful = set()
        for path in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
            token = str(path).strip()
            if token:
                successful.add(token)
        if not successful:
            try:
                for path in agentic_v2_successful_read_paths(history):
                    token = str(path).strip()
                    if token:
                        successful.add(token)
            except Exception:
                pass
        return successful

    def run(self, state: PipelineState) -> PipelineState:
        """Run path validation stage. Returns state with updated violations/contract."""
        deps = state.deps
        contract = state.contract
        history = state.history
        violations = state.violations
        tool = state.tool
        args = state.args
        action = state.action

        if action != "tool" or tool not in ("repo_read", "repo_list_files"):
            return state

        path_exists = deps["path_exists_repo_relative"]
        repo_readable = deps["repo_readable_evidence_file"]
        path_under_scope = deps["path_under_scope"]
        target_scope = str(contract.get("resolved_goal_scope") or "")

        # Path scope validation
        if target_scope and tool == "repo_list_files":
            raw_path = str(args.get("path") or ".")
            path = raw_path.strip()
            if path and not path_under_scope(path, target_scope):
                violations.append(f"repo_list_files_scope_mismatch:path={path}:expected_under={target_scope}")

        # Path existence validation
        if tool == "repo_read":
            raw_paths = args.get("paths", [args.get("path")]) if isinstance(args.get("paths"), list) else [args.get("path", "")]
            for raw_path in raw_paths:
                path = str(raw_path).strip()
                if not path:
                    continue
                if not path_exists(path):
                    violations.append(f"non_existing_path:{path}")
                elif not repo_readable(path):
                    violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")

        return state