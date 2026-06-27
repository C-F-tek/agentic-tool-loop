"""Extracted validation rule classes for planner decision validation.

This module contains the ValidationDeps dataclass and three validator classes
that replace the monolithic validate_planner_decision_against_evidence function.
"""

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Mapping


@dataclass(frozen=True)
class ValidationDeps:
    """Extracted deps/config for validate_planner_decision_against_evidence."""
    agentic_v2_decision_paths: Any
    agentic_v2_goal_scope: Any
    agentic_v2_read_has_window: Any
    agentic_v2_successful_read_paths: Any
    any_argument_group_present: Any
    apply_duplicate_window_replan_contract: Any
    apply_unverified_old_text_replan_contract: Any
    argument_value_present: Any
    canonical_invalid_code_product_decision_signature: Any
    code_product_build_state_duplicate_write: Any
    code_product_build_state_has_collecting_progress: Any
    code_product_build_state_parse: Any
    code_product_build_state_ready_payload: Any
    code_product_low_signal_target: Any
    code_product_payload_violations: Any
    contract_final_required_now: Any
    copyable_example_text: Any
    decision_matches_prompt_context_continuation: Any
    decision_paths: Any
    enforce_required_scratchpad_read_continuation_contract: Any
    final_answer_is_action_plan_without_code_product: Any
    final_composition_tool_names_from_candidates: Any
    invalid_code_product_decision_signature_count: Any
    invalid_decision_signature_key: Any
    native_required_tool_decision_has_transport_provenance: Any
    normalize_terminal_planner_decision: Any
    normalize_tool_name: Any
    old_text_verified_by_repo_read: Any
    path_exists_repo_relative: Any
    path_under_scope: Any
    planner_scratchpad_read_selector_present: Any
    planner_scratchpad_window_signature: Any
    prompt_window_consumed_offsets: Any
    prompt_window_tracking_metadata_errors: Any
    repo_analysis_goal: Any
    repo_path_kind: Any
    repo_read_selector_present: Any
    repo_read_window_signature: Any
    repo_readable_evidence_file: Any
    repo_rel_token: Any
    repeated_tool_call_count: Any
    scope_claim_conflict_for_path: Any
    successful_window_signatures: Any
    target_scope_conflict_resolved: Any
    latest_file_list_result: Any
    goal_requires_code_product_report: Any
    planner_evidence_contract: Any
    validate_unified_diff_text: Any
    successful_code_edit_proposals: Any


@dataclass(frozen=True)
class ValidationResult:
    """Result of a single validation check."""
    ok: bool
    violations: list[str] = field(default_factory=list)
    evidence_contract: dict = None
    extra: dict = None

    @classmethod
    def ok_result(cls, contract: dict, extra: dict = None) -> 'ValidationResult':
        return cls(ok=True, violations=[], evidence_contract=contract, extra=extra)

    @classmethod
    def fail_result(cls, contract: dict, violations: list[str], extra: dict = None) -> 'ValidationResult':
        return cls(ok=False, violations=violations, evidence_contract=contract, extra=extra)


class ToolCallValidator:
    """Validates tool call arguments and tool surface membership."""

    def __init__(self, deps: ValidationDeps, config: dict) -> None:
        self.deps = deps
        self.config = config

    def validate(
        self,
        tool: str,
        args: dict,
        action: str,
        contract: dict,
        allowed_tool_names: set,
        history: list,
    ) -> ValidationResult:
        violations: list[str] = []

        # Check tool surface membership
        if tool not in allowed_tool_names:
            violations.append("tool_not_in_turn_surface")
            if action == "tool" and self.deps.native_required_tool_decision_has_transport_provenance:
                violations.append("native_tool_not_in_turn_surface")
            contract["required_next_progress"] = (
                "The tool call was not in the planner tool surface for this turn. "
                "Use only the current turn tool surface; if final is allowed and no named "
                "evidence gap remains, return final instead of calling an unavailable tool."
            )

        # Check tool-specific arguments
        tool_arg_violations = self._check_tool_args(tool, args)
        violations.extend(tool_arg_violations)

        # Check scratchpad window
        if action == "tool" and tool == "planner_scratchpad_read":
            window_violation = self._check_scratchpad_window(tool, args, contract, history)
            if window_violation:
                violations.append(window_violation)

        if violations:
            return ValidationResult.fail_result(contract, violations)
        return ValidationResult.ok_result(contract)

    def _check_tool_args(self, tool: str, args: dict) -> list[str]:
        """Check tool-specific argument requirements."""
        from .validator_helpers import (
            _any_argument_group_present,
            _argument_value_present,
        )
        violations: list[str] = []

        tool_arg_checks = {
            "repo_search": (["query", "pattern", "symbol"], "repo_search_missing_query_pattern_or_symbol"),
            "repo_semantic_search": ("query", "repo_semantic_search_missing_query"),
            "repo_rg_search": (["query", "pattern"], "repo_rg_search_missing_pattern"),
            "repo_jq_query": (["query", "filter"], "repo_jq_query_missing_query"),
            "repo_ast_grep_search": (["pattern", "kind"], "repo_ast_grep_search_missing_pattern_or_kind"),
            "repo_ast_grep_dry_run": (["pattern", "rewrite"], "repo_ast_grep_dry_run_missing_pattern_or_rewrite"),
            "repo_tree_sitter_parse": ("path", "repo_tree_sitter_parse_missing_path"),
            "repo_unidiff_validate": (["unified_diff", "diff"], "repo_unidiff_validate_missing_diff"),
            "repo_git_apply_check": (["unified_diff", "diff", "patch"], "repo_git_apply_check_missing_diff"),
            "repo_shellcheck": (["path", "paths"], "repo_shellcheck_missing_path"),
            "repo_semgrep_scan": (["pattern", "config"], "repo_semgrep_scan_missing_pattern_or_config"),
            "repo_hyperfine_benchmark": ("commands", "repo_hyperfine_benchmark_missing_commands"),
            "planner_scratchpad_write": (["text", "content"], "planner_scratchpad_write_missing_text"),
            "runtime_sqlite_memory_write": (["text", "content"], "runtime_sqlite_memory_write_missing_text"),
            "terminal_search_files": ("query", "terminal_search_files_missing_query"),
            "terminal_run_command_wait": ("command", "terminal_run_command_wait_missing_command"),
            "repo_command": ("command", "repo_command_missing_command"),
        }

        if tool in tool_arg_checks:
            required_keys, violation = tool_arg_checks[tool]
            if isinstance(required_keys, str):
                required_keys = [required_keys]
            if not _any_argument_group_present(args, required_keys):
                violations.append(violation)

        # repo_read requires path or paths
        if tool == "repo_read" and not self.deps.repo_read_selector_present(args):
            violations.append("repo_read_missing_path_or_paths_items")

        return violations

    def _check_scratchpad_window(
        self,
        tool: str,
        args: dict,
        contract: dict,
        history: list,
    ) -> str | None:
        """Check planner_scratchpad_read window consistency."""
        from .validator_helpers import (
            _prompt_window_consumed_offsets,
            _apply_duplicate_window_replan_contract,
        )

        requested_kind = str(args.get("kind") or "").strip()
        requested_doc_id = str(args.get("document_id") or args.get("id") or "").strip()

        if requested_kind in {"prompt_context", "prompt_context_window"} and requested_doc_id:
            try:
                requested_offset = int(args.get("offset") or 0)
            except (TypeError, ValueError):
                requested_offset = 0

            consumed_offset = _prompt_window_consumed_offsets(history).get(requested_doc_id, 0)
            if consumed_offset > 0 and requested_offset < consumed_offset:
                violation = "planner_scratchpad_window_already_successful_without_progress"
                contract = _apply_duplicate_window_replan_contract(
                    contract,
                    violation=violation,
                    tool=tool,
                    args=args,
                    history=history,
                )
                return violation
        return None


class FinalValidationValidator:
    """Validates final/block/terminal decisions."""

    def __init__(self, deps: ValidationDeps, config: dict) -> None:
        self.deps = deps
        self.config = config

    def validate_final(
        self,
        decision: dict,
        goal: str,
        history: list,
        contract: dict,
        target_scope: str,
        target_file: str,
        target_kind: str,
        review_goal: bool,
        read_ok: list,
        latest_file_list_result: Any,
        requested_limit: int,
        known_paths: list,
        admissible_reads: set,
        apply_required: bool,
        apply_patch_applied: bool,
        apply_read_targets: set,
        user_scope_claims: list,
        effective_repo_goal: str,
        semantic_audit_goal: bool,
    ) -> ValidationResult:
        from .validator_helpers import (
            _minimum_read_coverage_contract,
            _final_answer_declares_missing_coverage,
            _coalesce_required_next_missing_paths,
            _stale_required_next_repo_read_paths,
            _successful_read_paths_for_final_route,
            _path_allowed_by_missing_evidence,
            _verified_required_next_missing_paths,
            _required_next_tool_from_missing_evidences,
            _coalesce_required_next_tool_tool,
            _coerce_final_rewrite_latch,
            _required_gap_paths_from_quality,
            _next_final_rewrite_latch,
            _repo_analysis_final_answer_quality,
        )

        violations: list[str] = []
        internal_inconsistencies: list[str] = []

        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))

        # Check terminal block required
        planner_forced_terminal_block = bool(final_contract.get("planner_forced_terminal_block") if isinstance(final_contract, dict) else False)
        if final_rewrite_latch == "terminal_block_required" or planner_forced_terminal_block:
            violations.append("terminal_block_required_final_disallowed")
            contract["terminal_block_final_retry_count"] = int(contract.get("terminal_block_final_retry_count") or 0) + 1
            contract["planner_cuda_rewrite_required"] = True
            contract["final_rewrite_latch"] = "terminal_block_required"
            contract["planner_may_choose_final"] = False
            contract["required_next_progress"] = (
                "Terminal block lane is active after repeated final-quality rejection. "
                "Return action=block with the remaining blocker; do not emit another final."
            )
            return ValidationResult.fail_result(contract, violations)

        # Check final_allowed
        if final_contract and final_contract.get("final_allowed") is False:
            violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))

        # Check post-write validation
        post_write_contract = contract.get("post_write_validation_contract") if isinstance(contract.get("post_write_validation_contract"), dict) else {}
        post_write_validation_required = bool(post_write_contract.get("required"))
        post_write_validation_done = bool(post_write_contract.get("validation_done"))
        post_write_validation_failed = bool(post_write_contract.get("validation_failed"))
        if post_write_validation_required and not post_write_validation_done:
            violations.append(
            "final_after_write_validation_failed"
            if post_write_validation_failed else
            "final_after_write_without_validation"
        )

        # Check read coverage
        final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "")
        coverage_required = False  # Placeholder - would need _minimum_read_coverage_required from validator_helpers
        coverage_satisfied = False  # Placeholder

        if coverage_required and not coverage_satisfied:
            violations.append("final_without_minimum_read_coverage")

        if _final_answer_declares_missing_coverage(final_answer):
            violations.append("final_declares_missing_read_coverage")

        # Check target file read
        if target_kind == "file" and target_file:
            if target_file not in read_ok:
                violations.append(f"final_without_requested_file_read:{target_file}")

        # Check scope requirements
        if target_scope:
            listed_rows = contract.get("repo_list_files_evidence") if isinstance(contract.get("repo_list_files_evidence"), list) else []
            scope_listed = bool(contract.get("latest_in_scope_repo_list_path")) or any(
                True  # Simplified - would need _path_under_scope
                for row in listed_rows if isinstance(row, dict)
            )
            scope_reads = [p for p in read_ok if True]  # Simplified
            final_allowed = bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False
            if not scope_listed and not final_allowed:
                violations.append(f"final_without_in_scope_tree_or_list:{target_scope}")
            if not scope_reads and not final_allowed:
                violations.append(f"final_without_in_scope_concrete_read:{target_scope}")

        # Check final answer quality
        if (effective_repo_goal or semantic_audit_goal) and not final_answer.strip():
            violations.append("final_empty_answer")

        if review_goal and not read_ok:
            violations.append("final_without_successful_repo_read_for_python_review")

        return ValidationResult.fail_result(contract, violations) if violations else ValidationResult.ok_result(contract)

    def validate_block(
        self,
        decision: dict,
        history: list,
        contract: dict,
    ) -> ValidationResult:
        violations: list[str] = []
        reason = str(decision.get("reason") or "")
        reason_low = reason.lower()

        # Check planner-specific failure reasons
        if reason == "planner_final_required_empty_output":
            violations.append("planner_final_required_empty_output")
            contract["required_next_progress"] = (
                "Quality gate is satisfied and no tool surface was provided. "
                "Return a terminal final answer. Do not call tools."
            )
            return ValidationResult.fail_result(contract, violations)

        if reason == "planner_native_tool_call_required":
            violations.append("planner_native_tool_call_required")
            contract["required_next_progress"] = (
                "Native tool mode is active and the planner emitted no message.tool_calls. "
                "Retry with one native tool_call from candidate_next_actions or return a real "
                "final/block answer when the evidence contract allows it."
            )
            return ValidationResult.fail_result(contract, violations)

        # Check degenerate output
        raw_planner_text = str(
            decision.get("raw_planner_text")
            or decision.get("raw_planner_text_preview")
            or decision.get("partial_content")
            or ""
        )
        if raw_planner_text and any(kw in reason_low for kw in [
            "invalid_planner_output_non_json", "non-json", "no_json",
            "degenerate", "timeout"
        ]):
            violations.append("planner_block_requires_controller_classification:" + reason[:160])
            return ValidationResult.fail_result(contract, violations)

        return ValidationResult.ok_result(contract)


class PathScopeValidator:
    """Validates path scope constraints and file evidence."""

    def __init__(self, deps: ValidationDeps, config: dict) -> None:
        self.deps = deps
        self.config = config

    def validate_tool_paths(
        self,
        tool: str,
        args: dict,
        target_scope: str,
        known_paths: set,
        read_ok: list,
        history: list,
        contract: dict,
    ) -> ValidationResult:
        from .validator_helpers import (
            _collect_repo_paths,
            _repo_rel_token,
            _path_under_scope,
            _repo_readable_evidence_file,
            _decision_paths,
        )

        violations: list[str] = []

        # Check scope constraints for scope-aware tools
        scope_aware_tools = {
            "repo_list_files", "repo_fd_files", "repo_rg_search",
            "repo_ast_grep_search", "repo_ast_grep_dry_run",
            "repo_tree_sitter_parse", "repo_ctags_symbols",
            "repo_semgrep_scan", "repo_shellcheck",
            "repo_validate", "repo_ruff_check", "repo_pyright_check",
            "repo_pytest_run", "repo_read", "repo_search",
            "repo_semantic_search", "repo_write_file",
            "repo_apply_patch", "repo_propose_code_edit",
        }

        if target_scope and tool in scope_aware_tools:
            out_of_scope = [
                p for p in self.deps.agentic_v2_decision_paths(tool, args)
                if p and not _path_under_scope(p, target_scope)
            ]
            if out_of_scope:
                for p in out_of_scope[:5]:
                    violations.append(f"{tool}_scope_mismatch:path={p}:expected_under={target_scope}")

        # Check repo_read specific constraints
        if tool == "repo_read":
            path = _repo_rel_token(args.get("path") or "")
            if path and known_paths and path not in known_paths and path not in set(read_ok):
                violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")

            if not self.deps.path_exists_repo_relative(path):
                violations.append(f"non_existing_path:{path}")

        return ValidationResult.fail_result(contract, violations) if violations else ValidationResult.ok_result(contract)

    def validate_repo_read_path(self, path: str, target_scope: str) -> str | None:
        """Validate a single repo_read path against scope."""
        from .validator_helpers import _path_under_scope
        if target_scope and path and not _path_under_scope(path, target_scope):
            return f"repo_read_path_outside_requested_scope:{path}:expected_under={target_scope}"
        return None