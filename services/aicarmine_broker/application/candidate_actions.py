"""Candidate next-action helpers for planner turn surface policy."""
from __future__ import annotations

import json
from typing import Any

from ..tool_contract import normalize_tool_name
from .code_product_state import CODE_PRODUCT_BUILD_STATE_KIND


def candidate_action_tool(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    return normalize_tool_name(str(action.get("tool") or ""))


def candidate_action_args(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    args = action.get("arguments")
    return args if isinstance(args, dict) else {}


def candidate_action_is_build_state_write(action: Any) -> bool:
    return (
        candidate_action_tool(action) == "planner_scratchpad_write"
        and str(candidate_action_args(action).get("kind") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def candidate_action_is_build_state_read(action: Any) -> bool:
    args = candidate_action_args(action)
    return (
        candidate_action_tool(action) == "planner_scratchpad_read"
        and str(args.get("kind") or args.get("mode") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def dedupe_candidate_actions(actions: list[Any], *, limit: int = 16) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = json.dumps(action, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
        if len(deduped) >= limit:
            break
    return deduped


def final_composition_tool_names_from_candidates(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = candidate_action_tool(action)
        args = candidate_action_args(action)
        if name == "planner_scratchpad_write" and str(args.get("kind") or "").strip() == "answer_chunk":
            names.add(name)
    return names
