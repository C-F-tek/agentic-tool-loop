"""Planner turn tool-surface policy."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...tool_contract import normalize_tool_name
from ..code_product.state import code_product_action_has_complete_payload
from ..evidence.goal_classifier import goal_requests_apply
from ..shared.diagnostics import diagnostic_row, safe_text
from .candidate_actions import (
    candidate_action_args,
    candidate_action_is_build_state_read,
    candidate_action_is_build_state_write,
    candidate_action_tool,
    dedupe_candidate_actions,
    enforce_required_scratchpad_read_continuation_contract,
    final_composition_tool_names_from_candidates,
)
from .required_tool_call import canonical_required_tool_call_key


OrderToolNames = Callable[[set[str]], list[str]]


class ToolSurfacePolicy:
    """Owner for the per-turn planner tool surface.

    The policy mutates only the evidence contract it receives through the public
    ``apply`` method. Tool-name ordering stays private so callers cannot mutate
    the surface halfway through a turn.
    """

    _REPO_DISCOVERY_TOOLS = {
        "repo_read",
        "repo_list_files",
        "repo_tree",
        "repo_search",
        "repo_semantic_search",
        "repo_fd_files",
        "repo_rg_search",
    }
    _AST_DIFF_TOOLS = {
        "repo_ast_grep_search",
        "repo_ast_grep_dry_run",
        "repo_tree_sitter_parse",
        "repo_unidiff_validate",
        "repo_git_apply_check",
    }
    _VALIDATION_TOOLS = {
        "repo_validate",
        "repo_ruff_check",
        "repo_pyright_check",
        "repo_pytest_run",
    }
    _NON_TERMINAL_SUPPORT_TOOLS = {
        "repo_read",
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
    }
    _ALWAYS_AVAILABLE_SUPPORT_TOOLS = {
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
    }

    def __init__(self, *, order_tool_names: OrderToolNames) -> None:
        self._order_tool_names = order_tool_names

    def tools_for_turn(
        self,
        *,
        goal: str,
        evidence_contract: dict[str, Any],
        intrinsic_context: dict[str, Any],
        prompt_context_continuation_required: dict[str, Any] | None = None,
    ) -> list[str]:
        contract = evidence_contract if isinstance(evidence_contract, dict) else {}
        continuation_tools = self._continuation_tool_only(prompt_context_continuation_required)
        if continuation_tools is not None:
            return self._ordered(set(continuation_tools))
        required_tools = self._continuation_tool_only(
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else None
        )
        if (
            required_tools is not None
            and self._required_call_is_deterministically_validated(contract)
            and not self._required_call_is_marked_satisfied(contract)
        ):
            return self._ordered(set(required_tools))

        rewrite_latch_tools = self._rewrite_latch_tools(contract)
        if rewrite_latch_tools is not None:
            return self._ordered(set(rewrite_latch_tools))

        if self._contract_coverage_required(contract) and not self._contract_coverage_satisfied(contract):
            names = set(self._REPO_DISCOVERY_TOOLS)
            names.update(self._NON_TERMINAL_SUPPORT_TOOLS)
            return self._ordered(names)

        if self._terminal_policy_locks_surface(contract):
            terminal_policy_tools = self._policy_declared_tools(contract)
            if terminal_policy_tools is not None:
                return terminal_policy_tools

        policy_tools = self._policy_declared_tools(contract)
        if policy_tools is not None:
            return policy_tools

        if self._contract_final_required_now(contract):
            names = final_composition_tool_names_from_candidates(contract)
            names.update(self._ALWAYS_AVAILABLE_SUPPORT_TOOLS)
            return self._ordered(names)

        semantic = contract.get("semantic_goal_classification") if isinstance(contract.get("semantic_goal_classification"), dict) else {}
        goal_class = safe_text(semantic.get("class"), limit=160).strip()
        code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        code_product_required = bool(code_contract.get("required"))
        apply_required = bool(contract.get("goal_requests_apply")) or goal_requests_apply(goal)
        names = self._base_tools_for_goal_class(
            goal_class=goal_class,
            code_product_required=code_product_required,
            apply_required=apply_required,
        )
        self._add_keyword_tools(names, goal)
        self._add_candidate_tools(names, contract)
        self._add_explicit_request_tool(names, intrinsic_context)
        candidate_names = self._candidate_tool_names(contract)
        if self._intrinsic_context_declares_selective_memory_gap(intrinsic_context):
            names.add("runtime_sqlite_memory_search")
        if "runtime_sqlite_memory_write" in candidate_names:
            names.add("runtime_sqlite_memory_write")
        return self._ordered(names)

    def apply(self, contract: dict[str, Any]) -> dict[str, Any]:
        """Keep candidate actions and native tools aligned with required progress."""
        if not isinstance(contract, dict):
            return diagnostic_row(
                "tool_surface_contract_not_object",
                schema="turn_tool_surface_policy_diagnostic.v1",
                received_type=type(contract).__name__,
                received_preview=safe_text(contract, limit=300),
            )
        surface_diagnostics: list[dict[str, Any]] = []
        raw_actions = contract.get("candidate_next_actions")
        if raw_actions not in (None, "", [], {}) and not isinstance(raw_actions, list):
            surface_diagnostics.append(diagnostic_row(
                "candidate_next_actions_not_list",
                schema="turn_tool_surface_policy_diagnostic.v1",
                received_type=type(raw_actions).__name__,
            ))
        actions = (
            contract.get("candidate_next_actions")
            if isinstance(contract.get("candidate_next_actions"), list)
            else []
        )
        progress = safe_text(contract.get("required_next_progress"), limit=4000).strip().lower()

        policy: dict[str, Any] = {
            "schema": "planner_turn_tool_surface_policy.v1",
            "reason": "",
            "allowed_tool_names": [],
            "candidate_actions_filtered": False,
        }
        strict_code_product_payload = any(
            token in progress
            for token in (
                "route shift required after invalid repo_propose_code_edit payload",
                "no new source window",
                "no unread source window",
                "no remaining state window to read",
                "empty collecting_source writes are rejected",
                "do not write code_product_build_state without a complete payload",
                "do not write code_product_build_state again unless it contains a complete",
                "code_product_route_shift_target_already_read",
            )
        )
        if surface_diagnostics:
            policy["tool_surface_diagnostics"] = surface_diagnostics
        required = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        required_validated = self._required_call_is_deterministically_validated(contract)
        rewrite_latch = self._final_rewrite_latch(contract)
        if rewrite_latch:
            required_tool = self._required_next_tool_call_tool(required)
            if (
                required_tool in self._REPO_DISCOVERY_TOOLS
                and required_validated
                and not self._required_call_is_marked_satisfied(contract)
            ):
                arguments = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
                reason = safe_text(required.get("reason") or progress or "final_rewrite_latch", limit=900)
                action = {
                    "action_id": "final_rewrite_latch_required_tool:" + required_tool,
                    "tool": required_tool,
                    "arguments": arguments,
                    "reason": reason,
                    "source": safe_text(required.get("source") or "final_rewrite_latch", limit=160),
                    "independent_read_only": True,
                }
                contract["candidate_next_actions"] = [action]
                contract["required_next_tool_call"] = {
                    "tool": required_tool,
                    "arguments": arguments,
                    "reason": reason,
                    "source": action["source"],
                    "validated": True,
                    "validation_source": safe_text(
                        required.get("validation_source")
                        or contract.get("required_next_tool_call_validation_source")
                        or "deterministic_validator",
                        limit=160,
                    ),
                }
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = contract["required_next_tool_call"]["validation_source"]
                final_contract = (
                    contract.get("finalization_contract")
                    if isinstance(contract.get("finalization_contract"), dict)
                    else {}
                )
                final_contract_planner_forced_block = final_contract.get("planner_forced_terminal_block")
                planner_forced_terminal_block = False
                if isinstance(final_contract_planner_forced_block, dict):
                    planner_forced_terminal_block = bool(final_contract_planner_forced_block.get("enabled"))
                elif final_contract_planner_forced_block is True:
                    planner_forced_terminal_block = True
                final_contract["final_allowed"] = False
                final_contract["planner_may_choose_final"] = False
                contract["planner_may_choose_final"] = False
                if planner_forced_terminal_block:
                    contract["planner_may_choose_block"] = True
                    final_contract["planner_may_choose_block"] = True
                else:
                    contract["planner_may_choose_block"] = False
                contract["turn_tool_surface_policy"] = {
                    **policy,
                    "reason": "final_rewrite_latch_required_tool",
                    "allowed_tool_names": [required_tool],
                    "candidate_actions_filtered": True,
                    "required_next_tool_call": contract.get("required_next_tool_call"),
                    "final_rewrite_latch": rewrite_latch,
                }
                contract["finalization_contract"] = final_contract
                return contract
            if required and not required_validated:
                contract["required_next_tool_call_advisory"] = required
                contract.pop("required_next_tool_call", None)
                contract.pop("required_next_tool_call_validated", None)
                contract.pop("required_next_tool_call_validation_source", None)
                policy["required_next_tool_call_unvalidated_advisory"] = True
            final_contract = (
                contract.get("finalization_contract")
                if isinstance(contract.get("finalization_contract"), dict)
                else {}
            )
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            contract["planner_may_choose_final"] = False
            policy.update(
                {
                    "reason": "final_rewrite_latch_no_required_tool_call",
                    "final_rewrite_latch": rewrite_latch,
                }
            )
            if rewrite_latch == "terminal_block_required":
                policy["locked_empty_tool_surface"] = True
                contract["planner_may_choose_block"] = True
                final_contract["planner_may_choose_block"] = True
                final_contract["reason"] = "final_rewrite_latch_terminal_block_required"
            else:
                final_contract["reason"] = "final_rewrite_latch_active"
            contract["finalization_contract"] = final_contract
            self._set_surface_only(contract, policy, set(), "final_rewrite_latch_lockout")
            return contract

        if required and self._required_call_is_marked_satisfied(contract):
            contract.pop("required_next_tool_call", None)
            contract.pop("required_next_tool_call_validated", None)
            contract.pop("required_next_tool_call_validation_source", None)
            required = {}
            required_validated = False
        if required.get("tool") == "planner_scratchpad_read" and required_validated:
            enforced = enforce_required_scratchpad_read_continuation_contract(
                contract,
                {
                    "tool": "planner_scratchpad_read",
                    "arguments": (
                        required.get("arguments")
                        if isinstance(required.get("arguments"), dict)
                        else {}
                    ),
                    "reason": required.get("reason") or progress,
                },
            )
            contract.clear()
            contract.update(enforced)
            policy.update(
                {
                    "reason": "required_scratchpad_read_continuation",
                    "allowed_tool_names": ["planner_scratchpad_read"],
                    "candidate_actions_filtered": True,
                    "required_next_tool_call": contract.get("required_next_tool_call"),
                    "required_scratchpad_read_continuation": True,
                }
            )
            contract["turn_tool_surface_policy"] = policy
            return contract

        required_tool = normalize_tool_name(safe_text(required.get("tool"), limit=160))
        if required_tool in self._REPO_DISCOVERY_TOOLS and required_validated:
            arguments = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
            reason = safe_text(required.get("reason") or progress or "required_next_tool_call", limit=900).strip()
            action = {
                "action_id": "required_next_tool_call:" + required_tool,
                "tool": required_tool,
                "arguments": arguments,
                "reason": reason,
                "source": safe_text(required.get("source") or "required_next_tool_call", limit=160),
                "independent_read_only": True,
            }
            contract["candidate_next_actions"] = [action]
            contract["required_next_tool_call"] = {
                "tool": required_tool,
                "arguments": arguments,
                "reason": reason,
                "source": action["source"],
                "validated": True,
                "validation_source": safe_text(
                    required.get("validation_source")
                    or contract.get("required_next_tool_call_validation_source")
                    or "deterministic_validator",
                    limit=160,
                ),
            }
            contract["required_next_tool_call_validated"] = True
            contract["required_next_tool_call_validation_source"] = contract["required_next_tool_call"]["validation_source"]
            contract["planner_may_choose_final"] = False
            final_contract = (
                contract.get("finalization_contract")
                if isinstance(contract.get("finalization_contract"), dict)
                else {}
            )
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = "required_next_tool_call_pending"
            contract["finalization_contract"] = final_contract
            policy.update(
                {
                    "reason": "required_next_tool_call_pending",
                    "allowed_tool_names": [required_tool],
                    "candidate_actions_filtered": True,
                    "required_next_tool_call": contract.get("required_next_tool_call"),
                }
            )
            contract["turn_tool_surface_policy"] = policy
            return contract

        if required and not required_validated:
            contract["required_next_tool_call_advisory"] = required
            contract.pop("required_next_tool_call", None)
            contract.pop("required_next_tool_call_validated", None)
            contract.pop("required_next_tool_call_validation_source", None)
            policy["required_next_tool_call_unvalidated_advisory"] = True
            policy["reason"] = "required_next_tool_call_unvalidated_advisory"
            contract["turn_tool_surface_policy"] = policy

        if self._contract_coverage_required(contract) and not self._contract_coverage_satisfied(contract):
            coverage_actions = [
                item for item in actions
                if candidate_action_tool(item) in self._REPO_DISCOVERY_TOOLS
            ]
            reason = "minimum_read_coverage_required"
            if coverage_actions:
                self._set_actions(contract, policy, coverage_actions, reason)
                self._add_allowed_tools(contract, policy, set(self._REPO_DISCOVERY_TOOLS))
            else:
                self._set_surface_only(contract, policy, set(self._REPO_DISCOVERY_TOOLS), reason)
            coverage = (
                contract.get("minimum_read_coverage")
                if isinstance(contract.get("minimum_read_coverage"), dict)
                else {}
            )
            missing = coverage.get("missing_owner_paths") or contract.get("missing_owner_paths") or []
            contract["required_next_progress"] = (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false. "
                "Choose a selective repo_read/repo_search/repo_list_files action for missing_owner_paths "
                f"{missing[:12] if isinstance(missing, list) else missing}, or return a typed block."
            )
            contract["turn_tool_surface_policy"] = policy
            return contract

        if self._contract_final_required_now(contract):
            final_actions = [
                item for item in actions
                if candidate_action_tool(item) == "planner_scratchpad_write"
                and str(candidate_action_args(item).get("kind") or "").strip() == "answer_chunk"
            ]
            self._set_actions(contract, policy, final_actions, "final_allowed_and_required_now")
            return contract

        code_contract = (
            contract.get("code_product_contract")
            if isinstance(contract.get("code_product_contract"), dict)
            else {}
        )
        apply_contract = (
            contract.get("apply_write_contract")
            if isinstance(contract.get("apply_write_contract"), dict)
            else {}
        )
        post_write_contract = (
            contract.get("post_write_validation_contract")
            if isinstance(contract.get("post_write_validation_contract"), dict)
            else {}
        )
        if post_write_contract.get("required") and not post_write_contract.get("validation_done"):
            if post_write_contract.get("validation_failed"):
                allowed = set(self._VALIDATION_TOOLS)
                allowed.update({"repo_read", "repo_apply_patch"})
                self._set_actions(
                    contract,
                    policy,
                    actions[:16],
                    "post_write_validation_failed",
                )
                self._add_allowed_tools(contract, policy, allowed)
            else:
                validation_actions = [
                    item for item in actions
                    if candidate_action_tool(item) in self._VALIDATION_TOOLS
                ]
                if validation_actions:
                    self._set_actions(
                        contract,
                        policy,
                        validation_actions,
                        "post_write_validation_required",
                    )
                    self._add_allowed_tools(contract, policy, set(self._VALIDATION_TOOLS))
                else:
                    self._set_surface_only(
                        contract,
                        policy,
                        set(self._VALIDATION_TOOLS),
                        "post_write_validation_required",
                    )
            return contract

        apply_required = bool(contract.get("goal_requests_apply")) or bool(apply_contract.get("required"))
        if apply_required and not bool(apply_contract.get("patch_applied")):
            if "apply_write_target_not_resolved" in progress or "no resolved concrete existing target file" in progress:
                self._set_actions(contract, policy, [], "apply_write_target_not_resolved")
            elif "target acquisition mode" in progress or "unread apply target" in progress:
                read_actions = [
                    item for item in actions
                    if candidate_action_tool(item) == "repo_read"
                ]
                if read_actions:
                    self._set_actions(contract, policy, read_actions, "apply_write_target_read_required")
                else:
                    self._set_surface_only(
                        contract,
                        policy,
                        {"repo_read"},
                        "apply_write_target_read_required",
                    )
            elif "repo_apply_patch" in progress:
                patch_actions = [
                    item for item in actions
                    if candidate_action_tool(item) == "repo_apply_patch"
                ]
                if patch_actions:
                    self._set_actions(contract, policy, patch_actions, "apply_write_patch_required")
                    self._add_allowed_tools(contract, policy, {"repo_apply_patch", "repo_read"})
                else:
                    self._set_surface_only(
                        contract,
                        policy,
                        {"repo_apply_patch", "repo_read"},
                        "apply_write_patch_required_model_generated_payload",
                    )
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_apply_patch", "repo_read"},
                    "apply_write_patch_required_by_contract",
                )
            if not policy.get("allowed_tool_names"):
                policy["locked_empty_tool_surface"] = True
                contract["turn_tool_surface_policy"] = policy
            return contract

        if not code_contract.get("required"):
            return contract

        if "return action=block" in progress and "blocked_incomplete" in progress:
            self._set_actions(contract, policy, [], "code_product_build_state_blocked_incomplete")
        elif "call repo_propose_code_edit" in progress and (
            "ready_for_propose" in progress
            or "complete repo_propose_code_edit candidate" in progress
            or "complete payload from candidate_next_actions" in progress
        ):
            propose_actions = [
                item for item in actions
                if candidate_action_tool(item) == "repo_propose_code_edit"
                and code_product_action_has_complete_payload(item)
            ]
            if propose_actions:
                self._set_actions(contract, policy, propose_actions, "code_product_ready_for_propose")
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_propose_code_edit"},
                    "code_product_ready_for_propose_model_generated_payload",
                    suppress_support_expansion=True,
                )
        elif "read the internal code_product_build_state" in progress:
            self._set_actions(
                contract,
                policy,
                [item for item in actions if candidate_action_is_build_state_read(item)],
                "code_product_build_state_read_required",
            )
        elif (
            ("advance with one real step" in progress or "write code_product_build_state with new real progress" in progress)
            and ("call repo_propose_code_edit" in progress or "typed block" in progress)
        ):
            propose_actions = [
                item for item in actions
                if candidate_action_tool(item) == "repo_propose_code_edit"
                and code_product_action_has_complete_payload(item)
            ]
            build_state_actions = [
                item for item in actions if candidate_action_is_build_state_write(item)
            ]
            if strict_code_product_payload:
                build_state_actions = []
            mixed_actions = propose_actions + build_state_actions
            if mixed_actions:
                self._set_actions(
                    contract,
                    policy,
                    mixed_actions,
                    "code_product_mixed_real_progress_or_typed_block",
                    suppress_support_expansion=strict_code_product_payload,
                )
                if not propose_actions and "call repo_propose_code_edit" in progress:
                    self._add_allowed_tools(contract, policy, {"repo_propose_code_edit"})
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_propose_code_edit"} if strict_code_product_payload else {"repo_propose_code_edit", "planner_scratchpad_write"},
                    "code_product_mixed_real_progress_or_typed_block_model_generated_payload",
                    suppress_support_expansion=strict_code_product_payload,
                )
        elif (
            "persist an internal code_product_build_state" in progress
            or "write code_product_build_state" in progress
            or "code_product_build_state with real progress" in progress
        ):
            self._set_actions(
                contract,
                policy,
                [
                    item for item in actions
                    if candidate_action_is_build_state_write(item)
                    and not strict_code_product_payload
                ],
                "code_product_build_state_write_required",
                suppress_support_expansion=strict_code_product_payload,
            )
        elif "candidate_next_actions[0]" in progress and actions:
            first = actions[0] if isinstance(actions[0], dict) else {}
            self._set_actions(contract, policy, [first] if first else [], "required_candidate_next_actions_0")
        elif (
            ("target is already read" in progress or "already read" in progress)
            and ("do not repeat repo_read" in progress or "do not call repo_read" in progress)
        ):
            filtered = [
                item for item in actions
                if candidate_action_tool(item) not in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
                and not (
                    strict_code_product_payload
                    and candidate_action_tool(item) == "planner_scratchpad_write"
                )
            ]
            self._set_actions(contract, policy, filtered, "code_product_target_already_read_no_repo_navigation")
        elif "read the target with repo_read" in progress:
            filtered = [
                item for item in actions
                if candidate_action_tool(item) in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
            ]
            if filtered:
                self._set_actions(contract, policy, filtered, "code_product_target_read_required")
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_read", "repo_list_files", "repo_tree", "repo_search"},
                    "code_product_target_read_required",
                )
        elif "call repo_propose_code_edit" in progress:
            propose_actions = [
                item for item in actions
                if candidate_action_tool(item) == "repo_propose_code_edit"
                and code_product_action_has_complete_payload(item)
            ]
            if propose_actions:
                self._set_actions(contract, policy, propose_actions, "code_product_propose_required")
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_propose_code_edit"},
                    "code_product_propose_or_build_state_required",
                    suppress_support_expansion=True,
                )
        else:
            filtered = [
                item for item in actions
                if not (
                    candidate_action_tool(item) == "repo_propose_code_edit"
                    and not code_product_action_has_complete_payload(item)
                )
            ]
            if "do not repeat repo_read" in progress or "do not call repo_read" in progress:
                filtered = [item for item in filtered if candidate_action_tool(item) != "repo_read"]
            self._set_actions(contract, policy, filtered[:16], "code_product_remove_incomplete_or_repeated_candidates")

        if not policy.get("allowed_tool_names"):
            policy["locked_empty_tool_surface"] = True
        contract["turn_tool_surface_policy"] = policy
        return contract

    @classmethod
    def _candidate_tool_names(cls, contract: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
        for action in actions:
            if isinstance(action, dict):
                name = normalize_tool_name(safe_text(action.get("tool"), limit=160))
                if name:
                    names.add(name)
        return names

    @classmethod
    def _contract_final_required_now(cls, contract: dict[str, Any]) -> bool:
        contract = contract if isinstance(contract, dict) else {}
        if not cls._contract_coverage_satisfied(contract):
            return False
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        if final_contract.get("final_allowed") is not True:
            return False
        terminal_guidance = (
            contract.get("terminal_decision_guidance")
            if isinstance(contract.get("terminal_decision_guidance"), dict)
            else {}
        )
        if (
            terminal_guidance.get("terminal_decision_required") is True
            and terminal_guidance.get("tool_calls_allowed") is False
        ):
            return True
        if (
            final_contract.get("terminal_decision_required_by_step_budget") is True
            and final_contract.get("tool_calls_disallowed_by_step_budget") is True
        ):
            return True
        if final_contract.get("final_required") is True:
            return True
        return False

    @classmethod
    def _contract_coverage_required(cls, contract: dict[str, Any]) -> bool:
        contract = contract if isinstance(contract, dict) else {}
        coverage = (
            contract.get("minimum_read_coverage")
            if isinstance(contract.get("minimum_read_coverage"), dict)
            else {}
        )
        if coverage:
            return coverage.get("required") is True
        return contract.get("coverage_satisfied") is not True

    @classmethod
    def _contract_coverage_satisfied(cls, contract: dict[str, Any]) -> bool:
        contract = contract if isinstance(contract, dict) else {}
        coverage = (
            contract.get("minimum_read_coverage")
            if isinstance(contract.get("minimum_read_coverage"), dict)
            else {}
        )
        if coverage:
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True

    @classmethod
    def _intrinsic_context_declares_selective_memory_gap(cls, intrinsic_context: dict[str, Any]) -> bool:
        if not isinstance(intrinsic_context, dict):
            return False
        for key in ("retrieved_memory", "retrieved_rag_chunks"):
            section = intrinsic_context.get(key)
            if not isinstance(section, dict):
                continue
            if section.get("gap") or section.get("available") is False:
                return True
        return False

    def _ordered(self, names: set[str]) -> list[str]:
        return self._order_tool_names({
            normalize_tool_name(safe_text(name, limit=160))
            for name in names
            if normalize_tool_name(safe_text(name, limit=160))
        })

    def _continuation_tool_only(self, continuation: dict[str, Any] | None) -> list[str] | None:
        continuation = continuation if isinstance(continuation, dict) else {}
        tool = normalize_tool_name(safe_text(continuation.get("tool"), limit=160))
        if tool == "planner_scratchpad_read":
            return ["planner_scratchpad_read"]
        if tool in self._REPO_DISCOVERY_TOOLS:
            return [tool]
        return None

    @staticmethod
    def _required_next_tool_call_tool(required: dict[str, Any]) -> str:
        required = required if isinstance(required, dict) else {}
        return normalize_tool_name(safe_text(required.get("tool"), limit=160))

    @classmethod
    def _final_rewrite_latch(cls, contract: dict[str, Any]) -> str:
        contract = contract if isinstance(contract, dict) else {}
        latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
        if latch in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
            return latch
        return ""

    def _rewrite_latch_tools(self, contract: dict[str, Any]) -> list[str] | None:
        contract = contract if isinstance(contract, dict) else {}
        latch = self._final_rewrite_latch(contract)
        if not latch:
            return None
        required = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        if self._required_call_is_marked_satisfied(contract):
            return None
        required_tool = self._required_next_tool_call_tool(required)
        if required_tool in self._REPO_DISCOVERY_TOOLS and self._required_call_is_deterministically_validated(contract):
            return [required_tool]
        if latch in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
            return []
        return None

    def _policy_declared_tools(self, contract: dict[str, Any]) -> list[str] | None:
        surface_policy = (
            contract.get("turn_tool_surface_policy")
            if isinstance(contract.get("turn_tool_surface_policy"), dict)
            else {}
        )
        policy_allowed = surface_policy.get("allowed_tool_names")
        if not isinstance(policy_allowed, list):
            return None
        if surface_policy.get("required_scratchpad_read_continuation"):
            return self._ordered({safe_text(name, limit=160) for name in policy_allowed})
        if policy_allowed or surface_policy.get("locked_empty_tool_surface") or self._contract_final_required_now(contract):
            names = {safe_text(name, limit=160) for name in policy_allowed}
            if self._contract_final_required_now(contract):
                names.update(self._ALWAYS_AVAILABLE_SUPPORT_TOOLS)
            elif not surface_policy.get("suppress_non_terminal_support_expansion"):
                names.update(self._NON_TERMINAL_SUPPORT_TOOLS)
            return self._ordered(names)
        return None

    def _terminal_policy_locks_surface(self, contract: dict[str, Any]) -> bool:
        surface_policy = (
            contract.get("turn_tool_surface_policy")
            if isinstance(contract.get("turn_tool_surface_policy"), dict)
            else {}
        )
        return bool(
            surface_policy.get("locked_empty_tool_surface")
            or self._contract_final_required_now(contract)
        )

    def _base_tools_for_goal_class(
        self,
        *,
        goal_class: str,
        code_product_required: bool,
        apply_required: bool,
    ) -> set[str]:
        names = set(self._REPO_DISCOVERY_TOOLS)
        if code_product_required:
            names.update(self._AST_DIFF_TOOLS)
            names.update({"repo_propose_code_edit", "planner_scratchpad_write"})
        elif apply_required:
            names.update(self._AST_DIFF_TOOLS)
            names.update(self._VALIDATION_TOOLS)
            names.update({"repo_apply_patch", "repo_command", "terminal_run_command_wait"})
        elif goal_class == "analysis_only":
            names = set(self._REPO_DISCOVERY_TOOLS)
            names.add("repo_ctags_symbols")
        else:
            names.add("repo_status")
        return names

    def _add_keyword_tools(self, names: set[str], goal: str) -> None:
        goal_low = safe_text(goal, limit=4000).lower()
        if any(token in goal_low for token in ("json", "payload", "schema", "openapi")):
            names.add("repo_jq_query")
        if any(token in goal_low for token in ("security", "sicurezza", "vulnerability", "vulnerabil", "sast", "semgrep")):
            names.add("repo_semgrep_scan")
        if any(token in goal_low for token in ("shell", "bash", ".sh", "shellcheck")):
            names.add("repo_shellcheck")
        if any(token in goal_low for token in ("benchmark", "performance", "prestazioni", "hyperfine")):
            names.add("repo_hyperfine_benchmark")

    def _add_candidate_tools(self, names: set[str], contract: dict[str, Any]) -> None:
        for candidate in self._candidate_tool_names(contract):
            if candidate.startswith("runtime_sqlite_memory_"):
                continue
            if candidate == "planner_scratchpad_read":
                continue
            names.add(candidate)

    def _add_explicit_request_tool(self, names: set[str], intrinsic_context: dict[str, Any]) -> None:
        if not isinstance(intrinsic_context, dict):
            return
        explicit = intrinsic_context.get("explicit_request_context")
        if not isinstance(explicit, dict):
            return
        target = normalize_tool_name(safe_text(explicit.get("target_internal_tool"), limit=160))
        if target:
            names.add(target)

    def _required_call_is_marked_satisfied(self, contract: dict[str, Any]) -> bool:
        required = contract.get("required_next_tool_call") if isinstance(contract.get("required_next_tool_call"), dict) else {}
        if not required:
            return False
        key = canonical_required_tool_call_key(required.get("tool"), required.get("arguments"))
        current = (
            contract.get("required_next_tool_call_satisfied")
            if isinstance(contract.get("required_next_tool_call_satisfied"), dict)
            else {}
        )
        current_key = current.get("key") or canonical_required_tool_call_key(
            current.get("tool"),
            current.get("arguments"),
        )
        if current.get("satisfied") is True and current_key == key:
            return True
        stale = contract.get("stale_required_next_tool_calls")
        for item in stale if isinstance(stale, list) else []:
            if not isinstance(item, dict):
                continue
            item_key = item.get("key") or canonical_required_tool_call_key(
                item.get("tool"),
                item.get("arguments"),
            )
            if item.get("satisfied") is True and item_key == key:
                return True
        return False

    @staticmethod
    def _required_call_is_deterministically_validated(contract: dict[str, Any]) -> bool:
        contract = contract if isinstance(contract, dict) else {}
        required = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        if not required:
            return False
        if required.get("validated") is True:
            return True
        return contract.get("required_next_tool_call_validated") is True

    def _set_actions(
        self,
        contract: dict[str, Any],
        policy: dict[str, Any],
        filtered: list[dict[str, Any]],
        reason: str,
        *,
        suppress_support_expansion: bool = False,
    ) -> None:
        filtered = dedupe_candidate_actions(filtered)
        contract["candidate_next_actions"] = filtered
        policy["candidate_actions_filtered"] = True
        policy["reason"] = reason
        if suppress_support_expansion:
            policy["suppress_non_terminal_support_expansion"] = True
        policy["allowed_tool_names"] = self._ordered({
            name for name in (candidate_action_tool(item) for item in filtered) if name
        })
        if len(filtered) == 1:
            policy["required_next_tool_call"] = {
                "tool": candidate_action_tool(filtered[0]),
                "arguments": candidate_action_args(filtered[0]),
                "reason": reason,
            }
        contract["turn_tool_surface_policy"] = policy

    def _set_surface_only(
        self,
        contract: dict[str, Any],
        policy: dict[str, Any],
        allowed_names: set[str],
        reason: str,
        *,
        suppress_support_expansion: bool = False,
    ) -> None:
        normalized_allowed = {
            normalize_tool_name(safe_text(name, limit=160))
            for name in allowed_names
            if normalize_tool_name(safe_text(name, limit=160))
        }

        existing_actions = (
            contract.get("candidate_next_actions")
            if isinstance(
                contract.get("candidate_next_actions"),
                list,
            )
            else []
        )

        kept_actions = [
            action
            for action in existing_actions
            if candidate_action_tool(action) in normalized_allowed
        ]
        removed_actions = [
            action
            for action in existing_actions
            if candidate_action_tool(action) not in normalized_allowed
        ]

        contract["candidate_next_actions"] = (
            dedupe_candidate_actions(kept_actions)
        )

        if removed_actions:
            stale_actions = (
                contract.get("stale_candidate_next_actions")
                if isinstance(
                    contract.get("stale_candidate_next_actions"),
                    list,
                )
                else []
            )

            contract["stale_candidate_next_actions"] = (
                dedupe_candidate_actions(
                    [
                        *removed_actions,
                        *stale_actions,
                    ]
                )[:32]
            )

        policy["candidate_actions_filtered"] = bool(
            removed_actions
        )
        policy["reason"] = reason

        if suppress_support_expansion:
            policy[
                "suppress_non_terminal_support_expansion"
            ] = True

        policy["allowed_tool_names"] = self._ordered(
            normalized_allowed
        )

        if not normalized_allowed:
            policy["locked_empty_tool_surface"] = True

        contract["turn_tool_surface_policy"] = policy
    def _add_allowed_tools(
        self,
        contract: dict[str, Any],
        policy: dict[str, Any],
        allowed_names: set[str],
    ) -> None:
        current = {
            normalize_tool_name(safe_text(name, limit=160))
            for name in policy.get("allowed_tool_names", [])
            if normalize_tool_name(safe_text(name, limit=160))
        }
        current.update({
            normalize_tool_name(safe_text(name, limit=160))
            for name in allowed_names
            if normalize_tool_name(safe_text(name, limit=160))
        })
        policy["allowed_tool_names"] = self._ordered(current)
        contract["turn_tool_surface_policy"] = policy


def candidate_tool_names(contract: dict[str, Any]) -> set[str]:
    return ToolSurfacePolicy._candidate_tool_names(contract)


def contract_final_required_now(contract: dict[str, Any]) -> bool:
    return ToolSurfacePolicy._contract_final_required_now(contract)


def intrinsic_context_declares_selective_memory_gap(intrinsic_context: dict[str, Any]) -> bool:
    return ToolSurfacePolicy._intrinsic_context_declares_selective_memory_gap(intrinsic_context)


def tool_surface_names_for_turn(
    *,
    goal: str,
    evidence_contract: dict[str, Any],
    intrinsic_context: dict[str, Any],
    order_tool_names: OrderToolNames,
    prompt_context_continuation_required: dict[str, Any] | None = None,
) -> list[str]:
    return ToolSurfacePolicy(order_tool_names=order_tool_names).tools_for_turn(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
        prompt_context_continuation_required=prompt_context_continuation_required,
    )


def apply_turn_surface_policy(contract: dict[str, Any], *, order_tool_names: OrderToolNames) -> dict[str, Any]:
    return ToolSurfacePolicy(order_tool_names=order_tool_names).apply(contract)
