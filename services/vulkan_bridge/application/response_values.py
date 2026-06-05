"""Pure response value helpers for the 3571 bridge."""
from __future__ import annotations

import json
from typing import Any


def compact_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if int(limit or 0) <= 0:
        return text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 64)] + "\n... <full result is available in inline payload fields when present>"


def json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def bridge_result_digest(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"preview": compact_text(result, 2000)} if result else {}
    keep: dict[str, Any] = {}
    for key in (
        "ok",
        "job_ok",
        "status",
        "job_id",
        "answer_for_30b",
        "summary_for_30b",
        "message_for_30b",
        "next_action_for_30b",
        "final_path",
        "final_markdown_path",
        "events_path",
        "full_result_available",
        "full_result_hint",
        "auto_finalized_by",
        "blocked_by",
        "rejected_tool",
        "blocked_tool",
        "error",
        "error_type",
    ):
        if result.get(key) not in (None, "", [], {}):
            keep[key] = result.get(key)
    history = result.get("history")
    if isinstance(history, list):
        keep["history_count"] = len(history)
    if isinstance(result.get("history_tail"), list):
        keep["history_tail"] = result.get("history_tail")[-5:]
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        keep["artifacts"] = [x for x in artifacts[:10] if isinstance(x, str)]
    return keep or {"preview": compact_text(result, 2000)}
