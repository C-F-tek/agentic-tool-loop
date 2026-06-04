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


def required_next_tool_call_from_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    tool = candidate_action_tool(action)
    args = candidate_action_args(action)
    if tool != "planner_scratchpad_read" or not args:
        return {}
    return {
        "tool": "planner_scratchpad_read",
        "arguments": {
            key: args.get(key)
            for key in ("kind", "document_id", "offset", "max_chars", "target_file")
            if args.get(key) not in (None, "", [], {})
        },
        "reason": action.get("reason"),
    }


def decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    if not isinstance(decision, dict) or not isinstance(continuation, dict):
        return True
    if continuation.get("tool") != "planner_scratchpad_read":
        return True
    if normalize_tool_name(str(decision.get("tool") or "")) != "planner_scratchpad_read":
        return False
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    expected = continuation.get("arguments") if isinstance(continuation.get("arguments"), dict) else {}
    expected_kind = str(expected.get("kind") or "prompt_context_window")
    if str(args.get("kind") or "") != expected_kind:
        return False
    if str(args.get("document_id") or "") != str(expected.get("document_id") or ""):
        return False
    try:
        if int(args.get("offset") or 0) != int(expected.get("offset") or 0):
            return False
        if expected.get("max_chars") not in (None, ""):
            return int(args.get("max_chars") or 0) == int(expected.get("max_chars") or 0)
        return True
    except (TypeError, ValueError):
        return False


def preserve_required_next_tool_call_for_prompt(
    payload: dict[str, Any],
    previous_evidence_contract: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or not isinstance(previous_evidence_contract, dict):
        return
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
    required = (
        previous_evidence_contract.get("required_next_tool_call")
        if isinstance(previous_evidence_contract.get("required_next_tool_call"), dict)
        else {}
    )
    if not required:
        return
    evidence["required_next_tool_call"] = required
    payload["required_next_tool_call"] = required
    for key in ("forbidden_repeated_tool_calls",):
        value = previous_evidence_contract.get(key)
        if isinstance(value, list) and value:
            evidence[key] = value
            payload[key] = value
    prev_actions = (
        previous_evidence_contract.get("candidate_next_actions")
        if isinstance(previous_evidence_contract.get("candidate_next_actions"), list)
        else []
    )
    current_actions = evidence.get("candidate_next_actions") if isinstance(evidence.get("candidate_next_actions"), list) else []
    required_key = json.dumps(required, ensure_ascii=False, sort_keys=True, default=str)
    matched_action = {}
    for action in prev_actions:
        if not isinstance(action, dict):
            continue
        action_required = required_next_tool_call_from_action(action)
        if json.dumps(action_required, ensure_ascii=False, sort_keys=True, default=str) == required_key:
            matched_action = action
            break
    if matched_action:
        action_key = json.dumps(matched_action, ensure_ascii=False, sort_keys=True, default=str)
        evidence["candidate_next_actions"] = [matched_action] + [
            item for item in current_actions
            if json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) != action_key
        ][:10]
    progress = previous_evidence_contract.get("required_next_progress")
    if progress not in (None, "", [], {}):
        evidence["required_next_progress"] = progress
    final_contract = evidence.get("finalization_contract") if isinstance(evidence.get("finalization_contract"), dict) else {}
    prev_final_contract = (
        previous_evidence_contract.get("finalization_contract")
        if isinstance(previous_evidence_contract.get("finalization_contract"), dict)
        else {}
    )
    if prev_final_contract.get("final_allowed") is False or required.get("tool") == "planner_scratchpad_read":
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = prev_final_contract.get("reason") or evidence.get("required_next_progress")
        evidence["planner_may_choose_final"] = False
    evidence["finalization_contract"] = final_contract
    payload["evidence_contract"] = evidence
