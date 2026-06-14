"""Shared metadata helpers for payload summaries and public pointers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()


def stable_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def stable_json_fingerprint(value: Any) -> tuple[int, str]:
    text = stable_json_text(value)
    return len(text), sha256_text(text)


def counted_list(value: Any, *, limit: int = 20) -> dict[str, Any]:
    if not isinstance(value, list):
        return {}
    shown = value[: max(0, int(limit or 0))]
    return {
        "count": len(value),
        "items": shown,
        "omitted_count": max(0, len(value) - len(shown)),
    }


def compact_value(
    value: Any,
    *,
    text_limit: int = 700,
    list_limit: int = 8,
    depth: int = 0,
) -> Any:
    if depth > 4:
        return str(value or "")[:text_limit]
    if isinstance(value, str):
        return value[:text_limit]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        out = [
            compact_value(item, text_limit=text_limit, list_limit=list_limit, depth=depth + 1)
            for item in value[: max(0, int(list_limit or 0))]
        ]
        if len(value) > list_limit:
            out.append({"omitted_count": len(value) - list_limit})
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            out[str(key)] = compact_value(
                item,
                text_limit=text_limit,
                list_limit=list_limit,
                depth=depth + 1,
            )
        return out
    return str(value or "")[:text_limit]
