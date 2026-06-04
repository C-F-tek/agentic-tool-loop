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
        continuation_tools = self._continuation_tool_only(prompt_context_continuation_required)
        if continuation_tools is not None:
            return continuation_tools

        contract = evidence_contract if isinstance(evidence_contract, dict) else {}
        policy_tools = self._policy_declared_tools(contract)
        if policy_tools is not None:
            return policy_tools

        if self._contract_final_required_now(contract):
            return self._ordered(final_composition_tool_names_from_candidates(contract))

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
            self._set_actions(contract, policy, propose_actions, "code_product_ready_for_propose")
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
            mixed_actions = [
                item for item in actions
                if (
                    candidate_action_tool(item) == "repo_propose_code_edit"
                    and code_product_action_has_complete_payload(item)
                )
                or candidate_action_is_build_state_write(item)
            ]
            self._set_actions(contract, policy, mixed_actions, "code_product_mixed_real_progress_or_typed_block")
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
        if policy_allowed or surface_policy.get("locked_empty_tool_surface") or self._contract_final_required_now(contract):
            return self._ordered({str(name) for name in policy_allowed})
        return None

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
