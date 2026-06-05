"""Prompt context window compaction helpers."""
from __future__ import annotations

from typing import Any, Callable

from .values import text_hash


PROMPT_CONTEXT_WINDOW_COMPACT_KEYS = (
    "document_id",
    "section",
    "store",
    "metadata",
    "window_start",
    "window_end",
    "full_chars",
    "window_chars",
    "complete",
    "has_more_before",
    "has_more_after",
    "sha256",
    "window_sha256",
    "text",
)

PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS = (
    "document_id",
    "section",
    "window_start",
    "window_end",
    "full_chars",
    "window_chars",
    "complete",
    "has_more_before",
    "has_more_after",
    "sha256",
    "window_sha256",
    "text",
)


def compact_prompt_context_window_item(item: dict[str, Any]) -> dict[str, Any]:
    compact_item: dict[str, Any] = {}
    for key in PROMPT_CONTEXT_WINDOW_COMPACT_KEYS:
        if key not in item:
            continue
        value = item.get(key)
        if value in (None, "", [], {}):
            continue
        compact_item[key] = str(value) if key == "text" else value
    if "window_sha256" not in compact_item and compact_item.get("text"):
        compact_item["window_sha256"] = text_hash(str(compact_item.get("text") or ""))
    return compact_item


def bounded_prompt_context_tool_result_payload(
    result: dict[str, Any],
    *,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if result.get("tool") != "planner_scratchpad_read":
        return {}
    mode = str(result.get("mode") or "")
    if mode not in {"prompt_context_window", code_product_build_state_kind}:
        return {}
    items = result.get("items") if isinstance(result.get("items"), list) else []
    payload: dict[str, Any] = {
        "schema": "planner_bounded_tool_result.v1",
        "tool": "planner_scratchpad_read",
        "ok": result.get("ok"),
        "mode": mode,
        "count": result.get("count", len(items)),
        "items": [
            compact_prompt_context_window_item(item)
            for item in items
            if isinstance(item, dict)
        ],
    }
    for key in ("kind", "target_file", "status", "complete_payload_ready", "state_parse_error"):
        if result.get(key) not in (None, "", [], {}):
            payload[key] = result.get(key)
    for item in payload.get("items") or []:
        if not isinstance(item, dict) or item.get("has_more_after") is not True:
            continue
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": mode,
                "document_id": item.get("document_id"),
                "offset": item.get("window_end"),
                "max_chars": item.get("window_chars"),
            },
        }
        if mode == code_product_build_state_kind and payload.get("target_file"):
            payload["planner_can_request_more"]["arguments"]["target_file"] = payload.get("target_file")
        break
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


HistoryToolResult = Callable[[dict[str, Any]], dict[str, Any]]
RequiredToolCallFromAction = Callable[[dict[str, Any]], dict[str, Any]]


def prompt_window_consumed_offsets(
    history: list[dict[str, Any]],
    *,
    history_tool_result: HistoryToolResult,
    code_product_build_state_kind: str,
) -> dict[str, int]:
    consumed: dict[str, int] = {}
    for row in history if isinstance(history, list) else []:
        result = history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", code_product_build_state_kind}:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            if any(key not in item for key in PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS):
                continue
            doc_id = str(item.get("document_id") or "").strip()
            if not doc_id:
                continue
            try:
                end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                end = 0
            if end > consumed.get(doc_id, 0):
                consumed[doc_id] = end
    return consumed


def prompt_window_tracking_metadata_errors(
    history: list[dict[str, Any]],
    *,
    history_tool_result: HistoryToolResult,
    code_product_build_state_kind: str,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for row in history if isinstance(history, list) else []:
        result = history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", code_product_build_state_kind}:
            continue
        items = result.get("items") if isinstance(result.get("items"), list) else []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({
                    "step": row.get("step"),
                    "item_index": index,
                    "error": "prompt_context_window_item_not_object",
                })
                continue
            missing = [
                key for key in PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS
                if key not in item or item.get(key) in (None, "")
            ]
            if missing:
                errors.append({
                    "step": row.get("step"),
                    "document_id": item.get("document_id"),
                    "item_index": index,
                    "missing": missing,
                    "error": "prompt_context_window_tracking_metadata_missing",
                })
    return errors


def prompt_context_continue_action(
    window: dict[str, Any],
    *,
    max_chars: int,
    reason: str,
    code_product_build_state_kind: str,
) -> dict[str, Any] | None:
    if not isinstance(window, dict) or window.get("has_more_after") is not True:
        return None
    doc_id = str(window.get("document_id") or "").strip()
    if not doc_id:
        return None
    try:
        offset = int(window.get("next_unconsumed_offset") or window.get("window_end") or 0)
    except (TypeError, ValueError):
        offset = int(window.get("window_end") or 0)
    metadata = window.get("metadata") if isinstance(window.get("metadata"), dict) else {}
    kind = (
        code_product_build_state_kind
        if metadata.get("kind") == code_product_build_state_kind
        else "prompt_context_window"
    )
    args: dict[str, Any] = {
        "kind": kind,
        "document_id": doc_id,
        "offset": offset,
        "max_chars": max(500, int(max_chars or 1000)),
    }
    if kind == code_product_build_state_kind and metadata.get("target_file"):
        args["target_file"] = metadata.get("target_file")
    return {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": args,
        "reason": reason,
    }


def planner_scratchpad_next_window_action_from_history(
    args: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    history_tool_result: HistoryToolResult,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    args = args if isinstance(args, dict) else {}
    document_id = str(args.get("document_id") or args.get("id") or "").strip()
    if not document_id:
        return {}
    latest_window: dict[str, Any] = {}
    for row in history if isinstance(history, list) else []:
        result = history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("document_id") or "") != document_id:
                continue
            try:
                item_end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                item_end = 0
            try:
                latest_end = int(latest_window.get("window_end") or 0)
            except (TypeError, ValueError):
                latest_end = 0
            if item_end >= latest_end:
                latest_window = dict(item)
    if not latest_window or latest_window.get("has_more_after") is not True:
        return {}
    consumed = prompt_window_consumed_offsets(
        history,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=code_product_build_state_kind,
    ).get(document_id, 0)
    try:
        current_end = int(latest_window.get("window_end") or 0)
    except (TypeError, ValueError):
        current_end = 0
    try:
        full_chars = int(latest_window.get("full_chars") or current_end)
    except (TypeError, ValueError):
        full_chars = current_end
    next_offset = max(consumed, current_end)
    if next_offset >= full_chars:
        return {}
    latest_window["next_unconsumed_offset"] = next_offset
    if str(args.get("kind") or "") == code_product_build_state_kind:
        metadata = latest_window.get("metadata") if isinstance(latest_window.get("metadata"), dict) else {}
        metadata = dict(metadata)
        metadata["kind"] = code_product_build_state_kind
        if args.get("target_file"):
            metadata["target_file"] = args.get("target_file")
        latest_window["metadata"] = metadata
    return prompt_context_continue_action(
        latest_window,
        max_chars=int(args.get("max_chars") or 2500),
        reason=(
            "Repeated SQLite window was already consumed; continue with the next real "
            "unconsumed window before deciding final or code-product output."
        ),
        code_product_build_state_kind=code_product_build_state_kind,
    ) or {}


def required_working_set_continuation_action(
    required_working_set: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
    history_tool_result: HistoryToolResult,
    code_product_build_state_kind: str,
) -> dict[str, Any] | None:
    consumed = prompt_window_consumed_offsets(
        history,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=code_product_build_state_kind,
    )
    windows: list[dict[str, Any]] = []
    for item in (required_working_set or {}).get("repo_reads") or []:
        if isinstance(item, dict) and isinstance(item.get("content_window"), dict):
            windows.append(item["content_window"])
    code_product = (required_working_set or {}).get("code_product")
    if isinstance(code_product, dict) and isinstance(code_product.get("unified_diff_window"), dict):
        windows.append(code_product["unified_diff_window"])
    build_state = (required_working_set or {}).get("code_product_build_state")
    if isinstance(build_state, dict) and build_state.get("has_more_after") is True:
        state_window = dict(build_state)
        state_window["metadata"] = {
            "kind": code_product_build_state_kind,
            "target_file": build_state.get("target_file"),
            "status": build_state.get("status"),
        }
        windows.append(state_window)
    for window in windows:
        doc_id = str(window.get("document_id") or "").strip()
        if not doc_id or window.get("has_more_after") is not True:
            continue
        try:
            current_end = int(window.get("window_end") or 0)
        except (TypeError, ValueError):
            current_end = 0
        try:
            full_chars = int(window.get("full_chars") or current_end)
        except (TypeError, ValueError):
            full_chars = current_end
        consumed_end = max(current_end, consumed.get(doc_id, 0))
        if consumed_end >= full_chars:
            continue
        window["next_unconsumed_offset"] = consumed_end
        return prompt_context_continue_action(
            window,
            max_chars=window_chars,
            reason=(
                "Continue consuming the real required_working_set SQLite window before "
                "deciding final or code-product output."
            ),
            code_product_build_state_kind=code_product_build_state_kind,
        )
    return None


def evidence_contract_continuation_action(
    evidence_contract: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
    history_tool_result: HistoryToolResult,
    code_product_build_state_kind: str,
) -> dict[str, Any] | None:
    window = evidence_contract.get("full_evidence_contract_window") if isinstance(evidence_contract, dict) else {}
    if not isinstance(window, dict) or window.get("has_more_after") is not True:
        return None
    doc_id = str(window.get("document_id") or "").strip()
    if not doc_id:
        return None
    try:
        current_end = int(window.get("window_end") or 0)
    except (TypeError, ValueError):
        current_end = 0
    try:
        full_chars = int(window.get("full_chars") or current_end)
    except (TypeError, ValueError):
        full_chars = current_end
    consumed_end = max(
        current_end,
        prompt_window_consumed_offsets(
            history,
            history_tool_result=history_tool_result,
            code_product_build_state_kind=code_product_build_state_kind,
        ).get(doc_id, 0),
    )
    if consumed_end >= full_chars:
        return None
    window["next_unconsumed_offset"] = consumed_end
    return prompt_context_continue_action(
        window,
        max_chars=window_chars,
        reason=(
            "Continue consuming the real evidence_contract SQLite window before "
            "deciding final or code-product output."
        ),
        code_product_build_state_kind=code_product_build_state_kind,
    )


def prompt_context_continuation_from_payload(
    payload: dict[str, Any],
    *,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
    required = evidence.get("required_next_tool_call") if isinstance(evidence.get("required_next_tool_call"), dict) else {}
    if required.get("tool") == "planner_scratchpad_read":
        args = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
        kind = str(args.get("kind") or "")
        if kind in {"prompt_context_window", code_product_build_state_kind} and str(args.get("document_id") or "").strip():
            return {
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": kind,
                    "document_id": str(args.get("document_id") or ""),
                    "offset": args.get("offset"),
                    "max_chars": args.get("max_chars"),
                    **({"target_file": args.get("target_file")} if args.get("target_file") else {}),
                },
                "reason": required.get("reason") or evidence.get("required_next_progress"),
            }
    actions = evidence.get("candidate_next_actions") if isinstance(evidence.get("candidate_next_actions"), list) else []
    first = actions[0] if actions and isinstance(actions[0], dict) else {}
    if first.get("tool") != "planner_scratchpad_read":
        return {}
    args = first.get("arguments") if isinstance(first.get("arguments"), dict) else {}
    kind = str(args.get("kind") or "")
    if kind not in {"prompt_context_window", code_product_build_state_kind} or not str(args.get("document_id") or "").strip():
        return {}
    return {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": kind,
            "document_id": str(args.get("document_id") or ""),
            "offset": args.get("offset"),
            "max_chars": args.get("max_chars"),
            **({"target_file": args.get("target_file")} if args.get("target_file") else {}),
        },
        "reason": first.get("reason"),
    }


def forbidden_repeated_prompt_window_calls(
    history: list[dict[str, Any]],
    continuation_action: dict[str, Any],
    *,
    history_tool_result: HistoryToolResult,
    required_next_tool_call_from_action: RequiredToolCallFromAction,
    code_product_build_state_kind: str,
) -> list[dict[str, Any]]:
    required = required_next_tool_call_from_action(continuation_action)
    required_args = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
    required_doc_id = str(required_args.get("document_id") or "").strip()
    if not required_doc_id:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for row in history if isinstance(history, list) else []:
        result = history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", code_product_build_state_kind}:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("document_id") or "").strip()
            if doc_id != required_doc_id:
                continue
            try:
                start = int(item.get("window_start") or 0)
                chars = int(item.get("window_chars") or 0)
                end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                continue
            key = (doc_id, start, chars)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": str(result.get("mode") or "prompt_context_window"),
                        "document_id": doc_id,
                        "offset": start,
                        "max_chars": chars,
                    },
                    "window_end": end,
                    "reason": "already_consumed",
                }
            )
    return out[-20:]
