"""Planner turn tool-surface policy."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..tool_contract import normalize_tool_name
from .candidate_actions import (
    candidate_action_args,
    candidate_action_is_build_state_read,
    candidate_action_is_build_state_write,
    candidate_action_tool,
    dedupe_candidate_actions,
)
from .code_product_state import code_product_action_has_complete_payload


OrderToolNames = Callable[[set[str]], list[str]]


def candidate_tool_names(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    for action in actions:
        if isinstance(action, dict):
            name = normalize_tool_name(str(action.get("tool") or ""))
            if name:
                names.add(name)
    return names


def contract_final_required_now(contract: dict[str, Any]) -> bool:
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


def apply_turn_surface_policy(contract: dict[str, Any], *, order_tool_names: OrderToolNames) -> dict[str, Any]:
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

    def set_actions(filtered: list[dict[str, Any]], reason: str) -> None:
        filtered = dedupe_candidate_actions(filtered)
        contract["candidate_next_actions"] = filtered
        policy["candidate_actions_filtered"] = True
        policy["reason"] = reason
        policy["allowed_tool_names"] = order_tool_names({
            name for name in (candidate_action_tool(item) for item in filtered) if name
        })
        if len(filtered) == 1:
            policy["required_next_tool_call"] = {
                "tool": candidate_action_tool(filtered[0]),
                "arguments": candidate_action_args(filtered[0]),
                "reason": reason,
            }

    def set_surface_only(allowed_names: set[str], reason: str) -> None:
        policy["candidate_actions_filtered"] = False
        policy["reason"] = reason
        policy["allowed_tool_names"] = order_tool_names({
            normalize_tool_name(str(name))
            for name in allowed_names
            if normalize_tool_name(str(name))
        })

    if contract_final_required_now(contract):
        final_actions = [
            item for item in actions
            if candidate_action_tool(item) == "planner_scratchpad_write"
            and str(candidate_action_args(item).get("kind") or "").strip() == "answer_chunk"
        ]
        set_actions(final_actions, "final_allowed_and_required_now")
        contract["turn_tool_surface_policy"] = policy
        return contract

    code_contract = (
        contract.get("code_product_contract")
        if isinstance(contract.get("code_product_contract"), dict)
        else {}
    )
    if not code_contract.get("required"):
        return contract

    if "return action=block" in progress and "blocked_incomplete" in progress:
        set_actions([], "code_product_build_state_blocked_incomplete")
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
        set_actions(propose_actions, "code_product_ready_for_propose")
    elif "read the internal code_product_build_state" in progress:
        read_actions = [item for item in actions if candidate_action_is_build_state_read(item)]
        set_actions(read_actions, "code_product_build_state_read_required")
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
        set_actions(mixed_actions, "code_product_mixed_real_progress_or_typed_block")
    elif (
        "persist an internal code_product_build_state" in progress
        or "write code_product_build_state" in progress
        or "code_product_build_state with real progress" in progress
    ):
        write_actions = [item for item in actions if candidate_action_is_build_state_write(item)]
        set_actions(write_actions, "code_product_build_state_write_required")
    elif "candidate_next_actions[0]" in progress and actions:
        first = actions[0] if isinstance(actions[0], dict) else {}
        set_actions([first] if first else [], "required_candidate_next_actions_0")
    elif (
        ("target is already read" in progress or "already read" in progress)
        and ("do not repeat repo_read" in progress or "do not call repo_read" in progress)
    ):
        filtered = [
            item for item in actions
            if candidate_action_tool(item) not in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
        ]
        set_actions(filtered, "code_product_target_already_read_no_repo_navigation")
    elif "read the target with repo_read" in progress:
        filtered = [
            item for item in actions
            if candidate_action_tool(item) in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
        ]
        if filtered:
            set_actions(filtered, "code_product_target_read_required")
        else:
            set_surface_only({"repo_read", "repo_list_files", "repo_tree", "repo_search"}, "code_product_target_read_required")
    elif "call repo_propose_code_edit" in progress:
        propose_actions = [
            item for item in actions
            if candidate_action_tool(item) == "repo_propose_code_edit"
            and code_product_action_has_complete_payload(item)
        ]
        if propose_actions:
            set_actions(propose_actions, "code_product_propose_required")
        else:
            set_surface_only({"repo_propose_code_edit", "planner_scratchpad_write"}, "code_product_propose_or_build_state_required")
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
        set_actions(filtered[:16], "code_product_remove_incomplete_or_repeated_candidates")

    allowed = policy.get("allowed_tool_names")
    if not allowed:
        policy["locked_empty_tool_surface"] = True
    contract["turn_tool_surface_policy"] = policy
    return contract
