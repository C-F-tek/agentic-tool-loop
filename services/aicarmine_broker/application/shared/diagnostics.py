"""Small bounded diagnostics helpers for shared planner payload shaping."""

from __future__ import annotations

import json
from typing import Any


def diagnostic_row(
    reason: str,
    *,
    schema: str = "planner_shared_diagnostic.v1",
    exc: Exception | None = None,
    **fields: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema": schema,
        "diagnostic_only": True,
        "reason": str(reason or "diagnostic"),
    }
    if exc is not None:
        row["error_type"] = type(exc).__name__
        row["error"] = safe_text(exc, limit=500)
    for key, value in fields.items():
        if value not in (None, "", [], {}):
            row[str(key)] = value
    return row


def safe_text(value: Any, *, limit: int = 700, fallback: str = "") -> str:
    try:
        text = str(value if value is not None else "")
    except Exception as exc:
        text = f"<unstringifiable:{type(exc).__name__}>"
    if limit <= 0:
        return fallback
    return text[:limit] if text else fallback


def safe_json_text(
    value: Any,
    *,
    reason: str,
    ensure_ascii: bool = False,
    sort_keys: bool = True,
    separators: tuple[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    try:
        text = json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            separators=separators,
            default=str,
        )
        return text, None
    except (TypeError, ValueError, RecursionError) as exc:
        diagnostic = diagnostic_row(
            reason,
            exc=exc,
            value_type=type(value).__name__,
            value_preview=safe_text(value, limit=500),
        )
        text = json.dumps(
            diagnostic,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            separators=separators,
            default=str,
        )
        return text, diagnostic
