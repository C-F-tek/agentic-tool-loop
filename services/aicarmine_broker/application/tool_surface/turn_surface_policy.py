"""Planner turn tool-surface policy."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...tool_contract import normalize_tool_name
from ..code_product.state import code_product_action_has_complete_payload
from ..evidence.goal_classifier import goal_requests_apply
from .candidate_actions import (
    candidate_action_args,
    candidate_action_is_build_state_read,
    candidate_action_is_build_state_write,
    candidate_action_tool,
    dedupe_candidate_actions,
    enforce_required_scratchpad_read_continuation_contract,
    final_composition_tool_names_from_candidates,
)


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
        if required_tools is not None:
            return self._ordered(set(required_tools))

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
        goal_class = str(semantic.get("class") or "").strip()
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
            return contract
        actions = (
            contract.get("candidate_next_actions")
            if isinstance(contract.get("candidate_next_actions"), list)
            else []
        )
        progress = str(contract.get("required_next_progress") or "").strip().lower()
        policy: dict[str, Any] = {
            "schema": "planner_turn_tool_surface_policy.v1",
            "reason": "",
            "allowed_tool_names": [],
            "candidate_actions_filtered": False,
        }
        required = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        if required.get("tool") == "planner_scratchpad_read":
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
            mixed_actions = propose_actions + build_state_actions
            if mixed_actions:
                self._set_actions(contract, policy, mixed_actions, "code_product_mixed_real_progress_or_typed_block")
                if not propose_actions and "call repo_propose_code_edit" in progress:
                    self._add_allowed_tools(contract, policy, {"repo_propose_code_edit"})
            else:
                self._set_surface_only(
                    contract,
                    policy,
                    {"repo_propose_code_edit", "planner_scratchpad_write"},
                    "code_product_mixed_real_progress_or_typed_block_model_generated_payload",
                )
        elif (
            "persist an internal code_product_build_state" in progress
            or "write code_product_build_state" in progress
            or "code_product_build_state with real progress" in progress
        ):
            self._set_actions(
                contract,
                policy,
                [item for item in actions if candidate_action_is_build_state_write(item)],
                "code_product_build_state_write_required",
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
                    {"repo_propose_code_edit", "planner_scratchpad_write"},
                    "code_product_propose_or_build_state_required",
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
                name = normalize_tool_name(str(action.get("tool") or ""))
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
        progress = str(contract.get("required_next_progress") or "").strip().lower()
        if "produce action=final" in progress:
            return True
        if "quality gate is satisfied" in progress and "final" in progress:
            return True
        operational = (
            contract.get("operational_notes")
            if isinstance(contract.get("operational_notes"), dict)
            else {}
        )
        next_instruction = str(operational.get("next_instruction") or "").strip().lower()
        return "produce action=final" in next_instruction

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
            normalize_tool_name(str(name))
            for name in names
            if normalize_tool_name(str(name))
        })

    def _continuation_tool_only(self, continuation: dict[str, Any] | None) -> list[str] | None:
        continuation = continuation if isinstance(continuation, dict) else {}
        if continuation.get("tool") == "planner_scratchpad_read":
            return ["planner_scratchpad_read"]
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
            return self._ordered({str(name) for name in policy_allowed})
        if policy_allowed or surface_policy.get("locked_empty_tool_surface") or self._contract_final_required_now(contract):
            names = {str(name) for name in policy_allowed}
            if self._contract_final_required_now(contract):
                names.update(self._ALWAYS_AVAILABLE_SUPPORT_TOOLS)
            else:
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
        goal_low = str(goal or "").lower()
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
        target = normalize_tool_name(str(explicit.get("target_internal_tool") or ""))
        if target:
            names.add(target)

    def _set_actions(
        self,
        contract: dict[str, Any],
        policy: dict[str, Any],
        filtered: list[dict[str, Any]],
        reason: str,
    ) -> None:
        filtered = dedupe_candidate_actions(filtered)
        contract["candidate_next_actions"] = filtered
        policy["candidate_actions_filtered"] = True
        policy["reason"] = reason
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
    ) -> None:
        policy["candidate_actions_filtered"] = False
        policy["reason"] = reason
        policy["allowed_tool_names"] = self._ordered(allowed_names)
        contract["turn_tool_surface_policy"] = policy

    def _add_allowed_tools(
        self,
        contract: dict[str, Any],
        policy: dict[str, Any],
        allowed_names: set[str],
    ) -> None:
        current = {
            normalize_tool_name(str(name))
            for name in policy.get("allowed_tool_names", [])
            if normalize_tool_name(str(name))
        }
        current.update({
            normalize_tool_name(str(name))
            for name in allowed_names
            if normalize_tool_name(str(name))
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
