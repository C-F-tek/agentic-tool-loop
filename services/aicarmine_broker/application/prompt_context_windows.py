"""Prompt context window compaction helpers."""
from __future__ import annotations

from typing import Any

from .prompt_values import text_hash


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
