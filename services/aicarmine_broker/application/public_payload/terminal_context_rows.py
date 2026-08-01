"""Pure terminal-context row helpersfrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

."""

from __future__ import annotations

from typing import Any


def terminal_context_alias() -> dict[str, Any]:
    return {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }


def _history_row_error(index: int, reason: str, exc: Exception | None = None) -> dict[str, Any]:
    row = {
        "schema": "terminal_context_row_diagnostic.v1",
        "diagnostic_only": True,
        "history_index": index,
        "reason": reason,
    }
    if exc is not None:
        row["error_type"] = type(exc).__name__
        row["error"] = str(exc)[:500]
    return row


def planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return [_history_row_error(-1, "history_not_list")]
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            rows.append(_history_row_error(index, "history_item_not_object"))
            continue
        try:
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            if not decision:
                continue
            rows.append({
                key: value
                for key, value in {
                    "step": item.get("step"),
                    "action": decision.get("action"),
                    "tool": decision.get("tool"),
                    "arguments": decision.get("arguments"),
                    "reason": decision.get("reason"),
                }.items()
                if value not in (None, "", [], {})
            })
        except Exception:
            rows.append(_history_row_error(index, "planner_decision_row_failed", exc))
    return rows


def validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return [_history_row_error(-1, "history_not_list")]
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            rows.append(_history_row_error(index, "history_item_not_object"))
            continue
        try:
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            if result.get("tool") != "controller_guard":
                continue
            if result.get("guard_type") != "planner_decision_validation":
                continue
            rows.append({
                key: value
                for key, value in {
                    "step": item.get("step"),
                    "violations": result.get("violations"),
                    "rejected_decision": result.get("rejected_decision"),
                    "evidence_contract_summary": result.get("evidence_contract_summary"),
                    "evidence_contract_sha256": result.get("evidence_contract_sha256"),
                    "evidence_contract_chars": result.get("evidence_contract_chars"),
                    "summary": result.get("summary"),
                }.items()
                if value not in (None, "", [], {})
            })
        except Exception:
            rows.append(_history_row_error(index, "validation_rejection_row_failed", exc))
    return rows


def executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return [_history_row_error(-1, "history_not_list")]
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            rows.append(_history_row_error(index, "history_item_not_object"))
            continue
        try:
            result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            tool = result.get("tool")
            if not tool or tool == "controller_guard":
                continue
            rows.append({
                key: value
                for key, value in {
                    "step": item.get("step"),
                    "tool": tool,
                    "ok": result.get("ok"),
                    "path": result.get("path"),
                    "count": result.get("count"),
                    "total_matches": result.get("total_matches"),
                    "items_total": result.get("items_total"),
                    "paths_total": result.get("paths_total"),
                }.items()
                if value not in (None, "", [], {})
            })
        except Exception:
            rows.append(_history_row_error(index, "executed_tool_row_failed", exc))
    return rows
