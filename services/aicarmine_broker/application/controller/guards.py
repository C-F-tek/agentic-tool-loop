"""Controller guard and rejection signature helpers."""
from __future__ import annotations

from typing import Any, Callable

from ..shared.history_queries import history_tool_result


SignatureKey = Callable[[dict[str, Any]], str]


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    wanted = str(kind or "").lower()
    count = 0
    for item in history:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if result.get("tool") != "controller_guard":
            continue
        combined = " ".join(
            str(x or "") for x in (result.get("summary"), decision.get("reason"))
        ).lower()
        if wanted and wanted in combined:
            count += 1
    return count


def controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    rejected = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments")
        if decision.get(k) not in (None, "", [], {})
    }
    return {
        "violations": [str(v) for v in violations],
        "rejected_decision": rejected,
    }


def controller_guard_rejection_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
    *,
    invalid_decision_signature_key: SignatureKey,
) -> int:
    key = invalid_decision_signature_key(signature)
    if not key:
        return 0
    count = 0
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "controller_guard":
            continue
        existing = result.get("invalid_decision_signature")
        if not isinstance(existing, dict) or not existing:
            existing = controller_guard_rejection_signature(
                {"violations": result.get("violations") if isinstance(result.get("violations"), list) else []},
                result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
            )
        if invalid_decision_signature_key(existing) == key:
            count += 1
    return count


def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    combined = " ".join(
        str(decision.get(k) or "").lower()
        for k in ("reason", "final_answer", "raw_planner_text", "raw_planner_text_preview")
    )
    markers = (
        "planner stream degenerate output", "planner forced stream degenerate output",
        "planner emitted non-repairable non-json output", "no_json_object_candidate",
        "dead_or_stop_token_output", "role_boundary_marker", "role-boundary",
        "<|endoftext|>", ".readbyte",
    )
    return any(marker in combined for marker in markers)
