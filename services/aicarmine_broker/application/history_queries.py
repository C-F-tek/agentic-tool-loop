"""Small planner history query helpers."""
from __future__ import annotations

from typing import Any


def history_has_tool(history: list[dict[str, Any]], tool_name: str) -> bool:
    for item in history:
        if not isinstance(item, dict):
            continue
        for field in ("tool_result", "decision"):
            value = item.get(field)
            if isinstance(value, dict) and value.get("tool") == tool_name:
                return True
    return False


def successful_code_edit_proposals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") == "repo_propose_code_edit" and result.get("ok") is True:
            proposals.append(result)
    return proposals


def failed_code_edit_proposal_validation_row(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    if result.get("tool") != "repo_propose_code_edit" or result.get("ok") is not False:
        return {}
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    errors = [
        str(error)
        for error in (result.get("errors") or [])
        if str(error).strip()
    ]
    violations: list[str] = []
    if any(error == "unified_diff_missing" for error in errors):
        violations.append("repo_propose_code_edit_missing_unified_diff")
    if any(
        error.startswith("unidiff_parse_")
        or error in {
            "invalid_unified_diff_markers",
            "unified_diff_target_missing",
            "code_product_payload_not_complete",
        }
        for error in errors
    ):
        violations.append("invalid_code_product_candidate")
    if not violations:
        violations.append("code_product_payload_not_complete")
    violations.extend(f"repo_propose_code_edit_tool_error:{error}" for error in errors[:6])
    violations.append("code_product_route_shift_required")
    return {
        "step": item.get("step"),
        "guard_type": "tool_result_validation",
        "summary": "repo_propose_code_edit_failed: " + "; ".join(errors or ["ok_false"]),
        "classification": None,
        "semantic_goal_classification": None,
        "next_instruction": (
            "Previous repo_propose_code_edit returned ok=false. Do not repeat that proposal. "
            "Change decision now: provide a parser-valid complete unified_diff, complete "
            "old_text/new_text, write code_product_build_state with real progress, or typed block."
        ),
        "action_plan_candidate": "",
        "raw_planner_text_preview": "",
        "violations": list(dict.fromkeys(violations)),
        "rejected_decision": decision,
    }
