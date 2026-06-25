"""Prompt window helpers for planner available-tool manifests."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Re-export from tool_contract for backward compatibility
from ..prompt.tool_contract import (
    available_tools_for_user_payload,
    hard_budget_tool_shape_examples_for_prompt,
    tool_shape_examples_for_prompt,
)


StorePromptTextWindow = Callable[..., dict[str, Any]]


def available_tools_window_pack(
    root: Path,
    *,
    goal: str,
    available_tools: Any,
    window_chars: int,
    reason: str,
    store_prompt_text_window: StorePromptTextWindow,
) -> dict[str, Any]:
    tools = available_tools if isinstance(available_tools, list) else []
    text = json.dumps(tools, ensure_ascii=False, indent=2, default=str)
    window = store_prompt_text_window(
        root,
        section="available_tools",
        text=text,
        query=goal,
        max_chars=window_chars,
        metadata={
            "kind": "available_tools_manifest",
            "format": "json",
            "reason": reason,
        },
    )
    summary: list[dict[str, Any]] = []
    for row in tools:
        if not isinstance(row, dict):
            continue
        item = {"name": row.get("name")}
        if row.get("transport"):
            item["transport"] = row.get("transport")
        if isinstance(row.get("required"), list) and row.get("required"):
            item["required"] = row.get("required")
        summary.append({k: v for k, v in item.items() if v not in (None, "", [], {})})
    payload: dict[str, Any] = {
        "schema": "planner_available_tools_window.v1",
        "tool_count": len(summary),
        "tool_names": [str(item.get("name")) for item in summary if item.get("name")],
        "summary": summary[:80],
        "window": window,
    }
    if len(summary) > 80:
        payload["summary_truncated"] = True
        payload["summary_omitted_count"] = len(summary) - 80
    if window.get("document_id") and window.get("has_more_after") is True:
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return payload


# Local alias for planner imports that expect underscore-prefixed name
_available_tools_window_pack = available_tools_window_pack