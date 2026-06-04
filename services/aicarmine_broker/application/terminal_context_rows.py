"""Pure terminal-context row helpers."""

from __future__ import annotations

from typing import Any


def terminal_context_alias() -> dict[str, Any]:
    return {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }


def planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
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
    return rows


def validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
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
                "evidence_contract": result.get("evidence_contract"),
                "summary": result.get("summary"),
            }.items()
            if value not in (None, "", [], {})
        })
    return rows


def executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
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
    return rows
