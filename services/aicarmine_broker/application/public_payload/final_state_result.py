"""Final-state result compaction helpers."""

from __future__ import annotations

from typing import Any, Callable


HistoryLedgerBuilder = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def compact_final_state_result(
    result: dict[str, Any] | None,
    
    history_ledger_builder: HistoryLedgerBuilder,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    compact_result: dict[str, Any] = {}
    for key in (
        "auto_finalized_by",
        "blocked_by",
        "rejected_tool",
        "blocked_tool",
        "error",
        "error_type",
    ):
        if result.get(key) not in (None, "", [], {}):
            compact_result[key] = result.get(key)
    history = result.get("history")
    if isinstance(history, list):
        compact_result["history_count"] = len(history)
        compact_result["history_tail"] = history_ledger_builder(history[-8:])
        diagnostics = result.get("agent_flow_diagnostics") if isinstance(result.get("agent_flow_diagnostics"), dict) else {}
        if diagnostics:
            compact_result["agent_flow_diagnostics"] = diagnostics
    decision = result.get("planner_decision")
    if isinstance(decision, dict):
        compact_result["planner_decision"] = {
            key: decision.get(key)
            for key in ("action", "tool", "reason", "selected_by_3572", "coerced_by_3572")
            if decision.get(key) not in (None, "", [], {})
        }
    return compact_result
