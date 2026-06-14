"""Required-next-tool-call state helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ...tool_contract import normalize_tool_name


ToolArgs = dict[str, Any]
DecisionPaths = Callable[[ToolArgs], list[str]]
SuccessfulPaths = Callable[[list[dict[str, Any]]], list[str]]
WindowSignature = Callable[[ToolArgs], str]
SuccessfulWindowSignatures = Callable[[list[dict[str, Any]], str], set[str]]


def canonical_required_tool_call_key(tool: Any, arguments: Any) -> str:
    """Stable key for comparing read/search requirements to executed calls."""
    name = normalize_tool_name(str(tool or ""))
    args = arguments if isinstance(arguments, dict) else {}
    payload = {
        "tool": name,
        "arguments": {
            str(key): args.get(key)
            for key in sorted(args, key=lambda item: str(item))
            if args.get(key) not in (None, "", [], {})
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _history_tool_result(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    result = row.get("tool_result")
    return result if isinstance(result, dict) else {}


def _history_decision_args(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    decision = row.get("decision")
    decision = decision if isinstance(decision, dict) else {}
    args = decision.get("arguments")
    return args if isinstance(args, dict) else {}


def _successful_identical_tool_call(history: list[dict[str, Any]], tool: str, args: ToolArgs) -> bool:
    expected = canonical_required_tool_call_key(tool, args)
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if normalize_tool_name(str(result.get("tool") or "")) != tool or result.get("ok") is not True:
            continue
        if canonical_required_tool_call_key(tool, _history_decision_args(row)) == expected:
            return True
    return False


def required_next_tool_call_satisfaction(
    required_call: Any,
    history: list[dict[str, Any]],
    *,
    successful_repo_read_paths: SuccessfulPaths,
    successful_window_signatures: SuccessfulWindowSignatures,
    repo_read_window_signature: WindowSignature,
    planner_scratchpad_window_signature: WindowSignature,
    decision_paths: DecisionPaths,
) -> dict[str, Any]:
    """Return metadata describing whether a required route is already complete."""
    if not isinstance(required_call, dict):
        return {"schema": "required_next_tool_call_satisfaction.v1", "satisfied": False}
    tool = normalize_tool_name(str(required_call.get("tool") or ""))
    args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}
    status: dict[str, Any] = {
        "schema": "required_next_tool_call_satisfaction.v1",
        "satisfied": False,
        "tool": tool,
        "arguments": args,
        "key": canonical_required_tool_call_key(tool, args),
    }
    if not tool or not args:
        status["reason"] = "required_next_tool_call_missing_tool_or_arguments"
        return status

    if tool == "repo_read":
        signature = repo_read_window_signature(args)
        paths = decision_paths(args)
        status["paths"] = paths
        if signature:
            status["window_signature"] = signature
            if signature in successful_window_signatures(history, "repo_read"):
                status.update({"satisfied": True, "reason": "repo_read_window_already_successful"})
            else:
                status["reason"] = "repo_read_window_not_yet_successful"
            return status
        successful_paths = set(successful_repo_read_paths(history))
        if paths and all(path in successful_paths for path in paths):
            status.update({"satisfied": True, "reason": "repo_read_paths_already_successful"})
        else:
            status["reason"] = "repo_read_paths_not_yet_successful"
        return status

    if tool == "planner_scratchpad_read":
        signature = planner_scratchpad_window_signature(args)
        if signature:
            status["window_signature"] = signature
            if signature in successful_window_signatures(history, "planner_scratchpad_read"):
                status.update({"satisfied": True, "reason": "planner_scratchpad_window_already_successful"})
            else:
                status["reason"] = "planner_scratchpad_window_not_yet_successful"
            return status

    if tool in {
        "repo_semantic_search",
        "repo_rg_search",
        "repo_search",
        "repo_list_files",
        "planner_scratchpad_read",
    }:
        if _successful_identical_tool_call(history, tool, args):
            status.update({"satisfied": True, "reason": "identical_tool_call_already_successful"})
        else:
            status["reason"] = "identical_tool_call_not_yet_successful"
        return status

    status["reason"] = "tool_not_tracked_for_satisfaction"
    return status


def append_stale_required_call_marker(contract: dict[str, Any], status: dict[str, Any]) -> None:
    if not isinstance(contract, dict) or not isinstance(status, dict) or status.get("satisfied") is not True:
        return
    compact = {
        key: status.get(key)
        for key in ("tool", "arguments", "reason", "paths", "window_signature", "key")
        if status.get(key) not in (None, "", [], {})
    }
    compact["satisfied"] = True
    stale = contract.get("stale_required_next_tool_calls")
    stale = stale if isinstance(stale, list) else []
    if not any(
        isinstance(item, dict) and item.get("key") == compact.get("key")
        for item in stale
    ):
        stale.insert(0, compact)
    contract["stale_required_next_tool_calls"] = stale[:8]
    contract["required_next_tool_call_satisfied"] = compact
