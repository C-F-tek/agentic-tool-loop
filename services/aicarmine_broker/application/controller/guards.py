"""Controller guard and rejection sifrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

gnature helpers."""
from __future__ import annotations

import json
from typing import Any, Callable

from ...tool_contract import normalize_tool_name
from ..shared.history_queries import history_tool_result


SignatureKey = Callable[[dict[str, Any]], str]

SUPPORT_SUBTURN_TOOLS = frozenset({
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
})


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


def _stable_support_subturn_arguments(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    stable: dict[str, Any] = {}
    for key in (
        "kind",
        "mode",
        "tag",
        "section",
        "document_id",
        "target_file",
        "path",
        "offset",
        "max_chars",
        "query",
    ):
        value = args.get(key)
        if value not in (None, "", [], {}):
            stable[key] = value
    if tool == "planner_scratchpad_write":
        text = args.get("text") or args.get("content")
        if str(stable.get("kind") or "").strip() == "code_product_build_state" and isinstance(text, str):
            try:
                payload = json.loads(text)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key in ("target_file", "status"):
                    value = payload.get(key)
                    if value not in (None, "", [], {}) and key not in stable:
                        stable[key] = value
    return stable


def controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    tool = normalize_tool_name(str(decision.get("tool") or ""))
    rejected = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments")
        if decision.get(k) not in (None, "", [], {})
    }
    if tool in SUPPORT_SUBTURN_TOOLS:
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        rejected = {
            "action": str(decision.get("action") or "tool"),
            "tool": tool,
        }
        stable_args = _stable_support_subturn_arguments(tool, args)
        if stable_args:
            rejected["arguments"] = stable_args
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
