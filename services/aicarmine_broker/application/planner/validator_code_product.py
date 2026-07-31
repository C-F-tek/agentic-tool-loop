"""Code product validation stage extracted from validator.py.

Handles code product contract, edit_kind, unified_diff validation,
old_text verification, and placeholder detection.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.planner.validator_pipeline import PipelineState


class StageCodeProductValidation:
    """Validate code product proposals and edit payloads."""

    def run(self, state: PipelineState) -> PipelineState:
        """Run code product validation stage."""
        deps = state.deps
        contract = state.contract
        history = state.history
        violations = state.violations
        tool = state.tool
        args = state.args
        action = state.action
        goal = state.goal

        if action != "tool" or tool != "repo_propose_code_edit":
            return state

        code_product_contract = (
            contract.get("code_product_contract")
            if isinstance(contract.get("code_product_contract"), dict)
            else {}
        )
        read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]
        target_file = str(contract.get("resolved_goal_file") or "")
        target_scope = str(contract.get("resolved_goal_scope") or "")

        # Determine target paths
        paths = []
        if args.get("target_file"):
            paths.append(args.get("target_file"))
        elif args.get("path"):
            paths.append(args.get("path"))

        if not paths:
            violations.append("repo_propose_code_edit_missing_path_or_paths")
            return state

        # edit_kind validation
        edit_kind = str(args.get("edit_kind") or "")
        if edit_kind not in {"unified_diff", "structured_edit", "no_op"}:
            violations.append("repo_propose_code_edit_invalid_edit_kind")

        if not str(args.get("rationale") or "").strip():
            violations.append("repo_propose_code_edit_missing_rationale")

        # Target file read verification
        for path in paths:
            path = str(path).strip()
            if path and path not in read_ok:
                violations.append(f"code_product_target_not_read:{path}")

        # unified_diff validation
        if edit_kind == "unified_diff":
            diff_text = args.get("unified_diff")
            validate_unified_diff_text = deps["validate_unified_diff_text"]

            if not isinstance(diff_text, str) or not diff_text.strip():
                old_value = args.get("old_text")
                new_value = args.get("new_text")
                if not (isinstance(old_value, str) and isinstance(new_value, str)):
                    violations.append("repo_propose_code_edit_missing_unified_diff")
                elif self._copyable_example_text(old_value) or self._copyable_example_text(new_value):
                    violations.append("repo_propose_code_edit_placeholder_text")
                elif paths and not self._old_text_verified_by_repo_read(
                    history, paths[0], old_value if isinstance(old_value, str) else ""
                ):
                    violations.append("repo_propose_code_edit_old_text_not_from_verified_read")
            else:
                diff_errors = validate_unified_diff_text(
                    unified_diff=diff_text,
                    target_file=paths[0] if paths else "",
                    require_unidiff=True,
                )
                blocking_diff_errors = [
                    str(error)
                    for error in diff_errors
                    if str(error) != "unidiff_dependency_missing"
                ]
                if blocking_diff_errors:
                    violations.append("invalid_code_product_candidate")
                    violations.extend(
                        f"repo_propose_code_edit_unified_diff_error:{error}"
                        for error in blocking_diff_errors[:6]
                    )

        # structured_edit validation
        if edit_kind == "structured_edit" and not isinstance(args.get("structured_operations"), list):
            violations.append("repo_propose_code_edit_missing_structured_operations")

        # no_op validation
        if edit_kind == "no_op" and (
            args.get("unified_diff")
            or args.get("structured_operations")
            or args.get("old_text")
            or args.get("new_text")
        ):
            violations.append("repo_propose_code_edit_no_op_has_patch_payload")

        return state

    def _copyable_example_text(self, text: Any) -> bool:
        raw = str(text or "")
        return any(
            needle in raw.lower()
            for needle in ("example", "sample", "placeholder", "insert", "replace", "...")
        )

    def _old_text_verified_by_repo_read(self, history: list[dict[str, Any]], path: str, old_value: str) -> bool:
        if not old_value or not path:
            return False
        for row in history if isinstance(history, list) else []:
            if not isinstance(row, dict):
                continue
            result_row = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            if str(result_row.get("tool") or "") != "repo_read":
                continue
            content = result_row.get("content") or result_row.get("text") or ""
            if isinstance(content, str) and old_value in content:
                return True
        return False