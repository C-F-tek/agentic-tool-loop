"""Validator pipeline extracted from validator.py.

Decomposes the monolithic ``validate_planner_decision_against_evidence``
function into a sequence of focused pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal


@dataclass
class PipelineState:
    """Mutable state shared across pipeline stages."""
    goal: str = ""
    decision: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    deps: dict[str, Any] = field(default_factory=dict)

    # Normalized fields
    action: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    contract: dict[str, Any] = field(default_factory=dict)
    semantic_contract: dict[str, Any] = field(default_factory=dict)
    effective_repo_goal: str = ""
    semantic_audit_goal: str = ""

    # Validation results
    violations: list[str] = field(default_factory=list)
    internal_inconsistencies: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)

    # Coverage state
    coverage_required: bool = False
    coverage_satisfied: bool = True
    missing_owner_paths: list[str] = field(default_factory=list)


def _normalize_tool_name(tool: str) -> str:
    return str(tool or "").strip().lower()


def _repo_rel_token(value: Any) -> str:
    from aicarmine_broker.application.shared.path_tokens import repo_path_token
    return repo_path_token(value)


class StageNormalize:
    """Normalize decision and build evidence contract."""

    def run(self, state: PipelineState) -> PipelineState:
        deps = state.deps
        config = state.config

        # Extract deps
        for key in deps:
            locals()[f"_{key}"] = deps[key]

        state.decision = deps["normalize_terminal_planner_decision"](
            state.decision if isinstance(state.decision, dict) else {}
        )
        state.action = str(state.decision.get("action") or "tool").strip().lower()
        state.tool = _normalize_tool_name(str(state.decision.get("tool") or ""))
        state.args = state.decision.get("arguments") if isinstance(state.decision.get("arguments"), dict) else {}
        state.contract = deps["planner_evidence_contract"](state.goal, state.history)
        state.semantic_contract = (
            state.contract.get("semantic_goal_classification")
            if isinstance(state.contract.get("semantic_goal_classification"), dict)
            else {}
        )
        state.effective_repo_goal = effective_repo_analysis_goal(
            state.goal,
            state.semantic_contract,
            repo_analysis_goal=deps["repo_analysis_goal"],
        )
        state.semantic_audit_goal = goal_requests_semantic_audit(state.goal)
        return state


class StageFinalAction:
    """Validate final/done/complete actions."""

    def run(self, state: PipelineState) -> PipelineState:
        if state.action not in {"final", "done", "complete", "completed"}:
            return state

        deps = state.deps
        contract = state.contract
        violations = state.violations

        # Terminal block check
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        final_rewrite_latch = deps["coerce_final_rewrite_latch"](contract.get("final_rewrite_latch"))

        final_forced_block_payload = final_contract.get("planner_forced_terminal_block")
        planner_forced_terminal_block = False
        planner_forced_terminal_block_reason = ""
        if isinstance(final_forced_block_payload, dict):
            planner_forced_terminal_block = bool(final_forced_block_payload.get("enabled"))
            planner_forced_terminal_block_reason = str(final_forced_block_payload.get("reason") or "").strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        else:
            planner_forced_terminal_block = bool(final_forced_block_payload is True)
            planner_forced_terminal_block_reason = str(
                final_contract.get("planner_forced_terminal_block_reason") or ""
            ).strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        contract["finalization_contract"] = final_contract

        planner_may_choose_block = bool(contract.get("planner_may_choose_block")) or bool(
            final_contract.get("planner_may_choose_block")
        )
        if (final_rewrite_latch == "terminal_block_required" and planner_may_choose_block) or planner_forced_terminal_block:
            violations.append("terminal_block_required_final_disallowed")
            contract["terminal_block_final_retry_count"] = int(contract.get("terminal_block_final_retry_count") or 0) + 1
            contract["planner_cuda_rewrite_required"] = True
            contract["final_rewrite_latch"] = "terminal_block_required"
            contract["planner_may_choose_final"] = False
            contract["planner_may_choose_block"] = True
            contract["required_next_progress"] = (
                "Terminal block lane is active after repeated final-quality rejection. "
                "Return action=block with the remaining blocker; do not emit another final."
            )
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["planner_may_choose_block"] = True
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = (
                planner_forced_terminal_block_reason or "terminal_block_required_final_disallowed"
            )
            final_contract["reason"] = "terminal_block_required_final_disallowed"
            state.result = {"ok": False, "violations": violations, "evidence_contract": contract}
            return state

        if final_contract and final_contract.get("final_allowed") is False:
            violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))

        # Post-write validation
        post_write_contract = (
            contract.get("post_write_validation_contract")
            if isinstance(contract.get("post_write_validation_contract"), dict)
            else {}
        )
        if post_write_contract.get("required") and not post_write_contract.get("validation_done"):
            violations.append(
                "final_after_write_validation_failed"
                if post_write_contract.get("validation_failed")
                else "final_after_write_without_validation"
            )

        # Coverage check
        coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
        if not coverage:
            final_contract = (
                contract.get("finalization_contract")
                if isinstance(contract.get("finalization_contract"), dict)
                else {}
            )
            coverage = final_contract.get("minimum_read_coverage") if isinstance(final_contract.get("minimum_read_coverage"), dict) else {}
        state.coverage_required = coverage.get("required") is True if coverage else contract.get("coverage_satisfied") is not True
        state.coverage_satisfied = coverage.get("coverage_satisfied") is True if coverage else contract.get("coverage_satisfied") is True
        state.missing_owner_paths = [str(p) for p in coverage.get("missing_owner_paths", [])] if coverage else []

        if state.coverage_required and not state.coverage_satisfied:
            violations.append("final_without_minimum_read_coverage")
            contract["required_next_progress"] = (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false. "
                "Read/search the missing owner/core paths or return a typed block; do not final."
            )
            contract["coverage_block"] = {
                "schema": "minimum_read_coverage.block.v1",
                "coverage_satisfied": False,
                "missing_owner_paths": state.missing_owner_paths,
            }
            if isinstance(final_contract, dict):
                final_contract["final_allowed"] = False
                final_contract["planner_may_choose_final"] = False
                final_contract["coverage_satisfied"] = False
                final_contract["missing_owner_paths"] = state.missing_owner_paths
                contract["finalization_contract"] = final_contract
            contract["planner_may_choose_final"] = False

        state.result = {"ok": not violations, "violations": violations, "evidence_contract": contract}
        return state


class StageBlockAction:
    """Validate block/blocked/need_user actions."""

    def run(self, state: PipelineState) -> PipelineState:
        if state.action not in {"block", "blocked", "need_user", "needs_user"}:
            return state

        state.result = {"ok": True, "violations": [], "evidence_contract": state.contract}
        return state


class StageToolArguments:
    """Validate tool-specific argument presence."""

    TOOL_VALIDATORS = {
        "repo_search": (["query", "pattern", "symbol"], "repo_search_missing_query_pattern_or_symbol"),
        "repo_semantic_search": (["query"], "repo_semantic_search_missing_query"),
        "repo_rg_search": (["query", "pattern"], "repo_rg_search_missing_pattern"),
        "repo_jq_query": (["query", "filter"], "repo_jq_query_missing_query"),
        "repo_ast_grep_search": (["pattern", "kind"], "repo_ast_grep_search_missing_pattern_or_kind"),
        "repo_ast_grep_dry_run": (["pattern", "rewrite"], "repo_ast_grep_dry_run_missing_pattern_or_rewrite"),
        "repo_tree_sitter_parse": (["path"], "repo_tree_sitter_parse_missing_path"),
        "repo_unidiff_validate": (["unified_diff", "diff"], "repo_unidiff_validate_missing_diff"),
        "repo_git_apply_check": (["unified_diff", "diff", "patch"], "repo_git_apply_check_missing_diff"),
        "repo_shellcheck": (["path", "paths"], "repo_shellcheck_missing_path"),
        "repo_semgrep_scan": (["pattern", "config"], "repo_semgrep_scan_missing_pattern_or_config"),
        "repo_hyperfine_benchmark": (["commands"], "repo_hyperfine_benchmark_missing_commands"),
        "repo_read": (None, "repo_read_missing_path_or_paths_items"),  # Special handling
        "planner_scratchpad_write": (["text", "content"], "planner_scratchpad_write_missing_text"),
        "planner_scratchpad_read": (None, "planner_scratchpad_read_missing_selector"),  # Special handling
        "runtime_sqlite_memory_search": (["query", "tag", "kind"], "runtime_sqlite_memory_search_missing_query_tag_or_kind"),
        "runtime_sqlite_memory_write": (["text", "content"], "runtime_sqlite_memory_write_missing_text"),
        "terminal_search_files": (["query"], "terminal_search_files_missing_query"),
        "terminal_run_command_wait": (["command"], "terminal_run_command_wait_missing_command"),
        "repo_command": (["command"], "repo_command_missing_command"),
    }

    def _any_argument_group_present(self, args: dict, groups: list[list[str]]) -> bool:
        return any(any(args.get(k) for k in group) for group in groups)

    def _argument_value_present(self, args: dict, key: str) -> bool:
        return bool(args.get(key))

    def run(self, state: PipelineState) -> PipelineState:
        if state.action != "tool":
            return state

        deps = state.deps
        tool = state.tool
        args = state.args
        violations = state.violations

        if tool in self.TOOL_VALIDATORS:
            keys, violation_msg = self.TOOL_VALIDATORS[tool]
            if keys is None:  # Special handling for repo_read and planner_scratchpad_read
                if tool == "repo_read":
                    if not deps["repo_read_selector_present"](args):
                        violations.append(violation_msg)
                elif tool == "planner_scratchpad_read":
                    if not deps["planner_scratchpad_read_selector_present"](args):
                        violations.append(violation_msg)
            else:
                if not self._any_argument_group_present(args, [keys]):
                    violations.append(violation_msg)

        state.result = {"ok": not violations, "violations": violations, "evidence_contract": state.contract}
        return state


from aicarmine_broker.application.planner.validator_path_validation import StagePathValidation
from aicarmine_broker.application.planner.validator_code_product import StageCodeProductValidation
from aicarmine_broker.application.planner.validator_repeated_calls import StageRepeatedCallDetection
from aicarmine_broker.application.planner.validator_quality_gate import StageQualityGate
from aicarmine_broker.application.planner.validator_duplicate_recovery import StageDuplicateRecovery


class ValidatorPipeline:
    """Orchestrates the validation pipeline stages."""

    def __init__(self) -> None:
        self.normalize = StageNormalize()
        self.final_action = StageFinalAction()
        self.block_action = StageBlockAction()
        self.tool_arguments = StageToolArguments()
        self.path_validation = StagePathValidation()
        self.code_product = StageCodeProductValidation()
        self.repeated_calls = StageRepeatedCallDetection()
        self.quality_gate = StageQualityGate()
        self.duplicate_recovery = StageDuplicateRecovery()

    def run(
        self,
        goal: str,
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        deps: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        state = PipelineState(
            goal=goal,
            decision=decision,
            history=history,
            config=dict(config),
            deps=dict(deps),
        )

        # Stage 1: Normalize
        state = self.normalize.run(state)

        # Stage 2: Final action validation
        state = self.final_action.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 3: Block action validation
        state = self.block_action.run(state)
        if state.result and state.result.get("ok") is True and state.action in {"block", "blocked", "need_user", "needs_user"}:
            return state.result

        # Stage 4: Tool argument validation
        state = self.tool_arguments.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 5: Path validation
        state = self.path_validation.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 6: Code product validation
        state = self.code_product.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 7: Repeated call detection
        state = self.repeated_calls.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 8: Quality gate (full logic extracted)
        state = self.quality_gate.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        # Stage 9: Duplicate recovery
        state = self.duplicate_recovery.run(state)
        if state.result and state.result.get("ok") is False:
            return state.result

        return state.result or {
            "ok": not state.violations,
            "violations": state.violations,
            "evidence_contract": state.contract,
        }
