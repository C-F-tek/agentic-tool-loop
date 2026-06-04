"""Sanitizers for terminal payloads visible to OpenWebUI."""

from __future__ import annotations

import re
from typing import Any


PUBLIC_TERMINAL_POINTER_KEYS = {
    "artifact_path",
    "producer_artifact",
    "final_path",
    "events_path",
    "db",
    "db_path",
    "sqlite_path",
    "document_id",
    "evidence_contract",
    "raw_planner_text_preview",
    "raw_planner_text",
    "raw_text",
}


def public_terminal_content_key(key: Any) -> bool:
    return str(key or "").lower() in {
        "content",
        "content_view",
        "unified_diff",
        "structured_operations",
        "old_text",
        "new_text",
        "stdout",
        "stderr",
        "stdout_tail",
        "stderr_tail",
        "text",
    }


def public_terminal_sanitize_text(value: Any, *, content: bool = False) -> str:
    text = str(value or "")
    if not text:
        return ""
    if content:
        return text
    text = re.sub(r"\s+(?:backup_)?artifact=[^\s,}\]]+", "", text)
    text = re.sub(r'"(?:artifact|artifact_path|producer_artifact|document_id|db|db_path|sqlite_path)"\s*:\s*"[^"]*",?', "", text)
    text = re.sub(r"[A-Za-z]:\\[^\s,}\]]+", "[local_path_omitted]", text)
    text = re.sub(r"https?://(?:127\.0\.0\.1|localhost)[^\s,}\]]*", "[local_url_omitted]", text, flags=re.I)
    text = re.sub(r"\bqwen-agent-workspace[^\s,}\]]*", "[job_workspace_path_omitted]", text)
    text = re.sub(r"\bagent-jobs[^\s,}\]]*", "[job_path_omitted]", text)
    text = re.sub(r"\btool-results\\[^\s,}\]]*", "[tool_result_path_omitted]", text)
    text = re.sub(r"\S+\.sqlite\b", "[sqlite_path_omitted]", text, flags=re.I)
    return text


def public_terminal_sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 12:
        return {}
    key_text = str(key or "")
    if key_text.lower() in PUBLIC_TERMINAL_POINTER_KEYS:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for child_key, child_value in value.items():
            cleaned = public_terminal_sanitize_value(child_value, key=str(child_key), depth=depth + 1)
            if cleaned not in (None, "", [], {}):
                out[str(child_key)] = cleaned
        return out
    if isinstance(value, list):
        out_list: list[Any] = []
        for item in value:
            cleaned = public_terminal_sanitize_value(item, key=key_text, depth=depth + 1)
            if cleaned not in (None, "", [], {}):
                out_list.append(cleaned)
        return out_list
    if isinstance(value, str):
        return public_terminal_sanitize_text(
            value,
            content=public_terminal_content_key(key_text),
        )
    return value
