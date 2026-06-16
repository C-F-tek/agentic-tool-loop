"""Required-next-tool-call state helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...tool_contract import normalize_tool_name
from ..shared.diagnostics import diagnostic_row, safe_json_text, safe_text

_DISCOVERY_ROUTE_TOOLS = {
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
}

_DISCOVERY_ARG_ALIASES = {
    "limit": "max_results",
    "top_k": "max_results",
    "candidate_limit": "max_results",
}

_DISCOVERY_CONTROL_ARGS = {
    "rerank",
    "reindex",
    "max_chunk_chars",
}


ToolArgs = dict[str, Any]
DecisionPaths = Callable[[ToolArgs], list[str]]
SuccessfulPaths = Callable[[list[dict[str, Any]]], list[str]]
WindowSignature = Callable[[ToolArgs], str]
SuccessfulWindowSignatures = Callable[[list[dict[str, Any]], str], set[str]]


def canonical_required_tool_call_key(tool: Any, arguments: Any) -> str:
    """Stable key for comparing read/search requirements to executed calls."""
    name = normalize_tool_name(safe_text(tool, limit=160))
    args = arguments if isinstance(arguments, dict) else {}
    payload = {
        "tool": name,
        "arguments": {
            safe_text(key, limit=160): args.get(key)
            for key in sorted(args, key=lambda item: safe_text(item, limit=160))
            if args.get(key) not in (None, "", [], {})
        },
    }
    text, _diagnostic = safe_json_text(
        payload,
        reason="canonical_required_tool_call_key_json_failed",
        separators=(",", ":"),
    )
    return text


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


def _canonical_discovery_args(tool: str, args: ToolArgs) -> dict[str, Any]:
    if tool not in _DISCOVERY_ROUTE_TOOLS:
        return args if isinstance(args, dict) else {}
    if not isinstance(args, dict):
        return {}

    out: dict[str, Any] = {}
    for key, value in args.items():
        if value in (None, "", [], {}):
            continue

        raw_key = safe_text(key, limit=160)
        canonical_key = _DISCOVERY_ARG_ALIASES.get(raw_key, raw_key)
        if canonical_key in _DISCOVERY_CONTROL_ARGS:
            continue

        out[canonical_key] = value

    return out


def _successful_identical_tool_call(history: list[dict[str, Any]], tool: str, args: ToolArgs) -> bool:
    expected = canonical_required_tool_call_key(tool, args)
    for row in history if isinstance(history, list) else []:
        try:
            result = _history_tool_result(row)
            if normalize_tool_name(safe_text(result.get("tool"), limit=160)) != tool or result.get("ok") is not True:
                continue
            decision_args = _history_decision_args(row)
            if canonical_required_tool_call_key(tool, decision_args) == expected:
                return True
            if _successful_tool_call_satisfies_required_args(tool, args, decision_args):
                return True
        except Exception:
            continue
    return False


def _successful_tool_call_satisfies_required_args(
    tool: str,
    required_args: ToolArgs,
    executed_args: ToolArgs,
) -> bool:
    """Allow runtime-expanded read-only discovery calls to satisfy model routes."""
    if tool not in _DISCOVERY_ROUTE_TOOLS:
        return False
    if not isinstance(required_args, dict) or not isinstance(executed_args, dict):
        return False
    required_args = _canonical_discovery_args(tool, required_args)
    executed_args = _canonical_discovery_args(tool, executed_args)
    meaningful_required = {
        safe_text(key, limit=160): value
        for key, value in required_args.items()
        if value not in (None, "", [], {})
    }
    if not meaningful_required:
        return False
    for key, expected_value in meaningful_required.items():
        if key not in executed_args:
            return False
        actual_value = executed_args.get(key)
        if isinstance(expected_value, (int, float)) or isinstance(actual_value, (int, float)):
            try:
                if float(expected_value) != float(actual_value):
                    return False
                continue
            except (TypeError, ValueError):
                return False
        if safe_text(actual_value, limit=4000) != safe_text(expected_value, limit=4000):
            return False
    return True


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
        return {
            "schema": "required_next_tool_call_satisfaction.v1",
            "satisfied": False,
            "reason": "required_next_tool_call_invalid",
            "satisfaction_diagnostics": [
                diagnostic_row(
                    "required_next_tool_call_not_object",
                    schema="required_tool_call_diagnostic.v1",
                    received_type=type(required_call).__name__,
                    received_preview=safe_text(required_call, limit=300),
                )
            ],
            "diagnostic_only": True,
        }
    tool = normalize_tool_name(safe_text(required_call.get("tool"), limit=160))
    raw_args = required_call.get("arguments")
    args = raw_args if isinstance(raw_args, dict) else {}
    status: dict[str, Any] = {
        "schema": "required_next_tool_call_satisfaction.v1",
        "satisfied": False,
        "tool": tool,
        "arguments": args,
        "key": canonical_required_tool_call_key(tool, args),
    }
    if not tool or not args:
        status["reason"] = "required_next_tool_call_missing_tool_or_arguments"
        diagnostics = []
        if not tool:
            diagnostics.append(diagnostic_row(
                "required_next_tool_call_tool_missing",
                schema="required_tool_call_diagnostic.v1",
                received_preview=safe_text(required_call.get("tool"), limit=160),
            ))
        if raw_args not in (None, "", [], {}) and not isinstance(raw_args, dict):
            diagnostics.append(diagnostic_row(
                "required_next_tool_call_arguments_not_object",
                schema="required_tool_call_diagnostic.v1",
                received_type=type(raw_args).__name__,
                received_preview=safe_text(raw_args, limit=300),
            ))
        if diagnostics:
            status["satisfaction_diagnostics"] = diagnostics
            status["diagnostic_only"] = True
        return status

    if tool == "repo_read":
        try:
            signature = repo_read_window_signature(args)
            paths = decision_paths(args)
        except Exception as exc:
            status["reason"] = "required_next_tool_call_signature_failed"
            status["satisfaction_diagnostics"] = [
                diagnostic_row("repo_read_signature_or_paths_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
            ]
            return status
        status["paths"] = paths
        if signature:
            status["window_signature"] = signature
            try:
                successful_signatures = successful_window_signatures(history, "repo_read")
            except Exception as exc:
                status["reason"] = "required_next_tool_call_history_signature_failed"
                status["satisfaction_diagnostics"] = [
                    diagnostic_row("repo_read_successful_window_signatures_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
                ]
                return status
            if signature in successful_signatures:
                status.update({"satisfied": True, "reason": "repo_read_window_already_successful"})
            else:
                try:
                    successful_paths = set(successful_repo_read_paths(history))
                except Exception as exc:
                    status["reason"] = "required_next_tool_call_successful_paths_failed"
                    status["satisfaction_diagnostics"] = [
                        diagnostic_row("repo_read_successful_paths_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
                    ]
                    return status
                if paths and all(path in successful_paths for path in paths):
                    status.update({
                        "satisfied": True,
                        "reason": "repo_read_paths_already_successful_despite_window_mismatch",
                        "window_signature_matched": False,
                    })
                else:
                    status["reason"] = "repo_read_window_not_yet_successful"
            return status
        try:
            successful_paths = set(successful_repo_read_paths(history))
        except Exception as exc:
            status["reason"] = "required_next_tool_call_successful_paths_failed"
            status["satisfaction_diagnostics"] = [
                diagnostic_row("repo_read_successful_paths_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
            ]
            return status
        if paths and all(path in successful_paths for path in paths):
            status.update({"satisfied": True, "reason": "repo_read_paths_already_successful"})
        else:
            status["reason"] = "repo_read_paths_not_yet_successful"
        return status

    if tool == "planner_scratchpad_read":
        try:
            signature = planner_scratchpad_window_signature(args)
        except Exception as exc:
            status["reason"] = "required_next_tool_call_signature_failed"
            status["satisfaction_diagnostics"] = [
                diagnostic_row("scratchpad_signature_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
            ]
            return status
        if signature:
            status["window_signature"] = signature
            try:
                successful_signatures = successful_window_signatures(history, "planner_scratchpad_read")
            except Exception as exc:
                status["reason"] = "required_next_tool_call_history_signature_failed"
                status["satisfaction_diagnostics"] = [
                    diagnostic_row("scratchpad_successful_window_signatures_failed", schema="required_tool_call_diagnostic.v1", exc=exc)
                ]
                return status
            if signature in successful_signatures:
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
