"""Prompt value clipping and stable text hashing helpers."""
from __future__ import annotations

import hashlib
from typing import Any

from ...config import AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS


def prompt_clip_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "")
    max_chars = int(limit or AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 40)] + "... <prompt_preview_truncated>"


def prompt_clip_value(value: Any,  text_limit: int | None = None, list_limit: int = 12, depth: int = 0) -> Any:
    if depth > 4:
        return prompt_clip_text(value, text_limit)
    if isinstance(value, str):
        return prompt_clip_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        out = [
            prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit, depth=depth + 1)
            for item in value[:list_limit]
        ]
        if len(value) > list_limit:
            out.append({"omitted_items_for_prompt": len(value) - list_limit})
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            if key in {"content", "content_preview", "content_excerpt", "text", "text_preview", "stdout", "stderr", "raw_planner_text_preview"}:
                out[key] = prompt_clip_text(item, text_limit)
            elif key == "unified_diff":
                diff_text = str(item or "")
                out["unified_diff_present"] = bool(diff_text.strip())
                out["unified_diff_chars"] = len(diff_text)
                out["unified_diff_markers_present"] = all(marker in diff_text for marker in ("---", "+++", "@@"))
            elif key == "structured_operations":
                operations = item if isinstance(item, list) else []
                out["structured_operations_present"] = bool(operations)
                out["structured_operations_count"] = len(operations)
            else:
                out[str(key)] = prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit, depth=depth + 1)
        return out
    return prompt_clip_text(value, text_limit)


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()
