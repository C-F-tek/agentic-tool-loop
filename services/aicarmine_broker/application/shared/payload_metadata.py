"""Shared metadata helpers for paylofrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

ad summaries and public pointers."""

from __future__ import annotations

import hashlib
from typing import Any

from .diagnostics import diagnostic_row, safe_json_text, safe_text


def sha256_text(text: str) -> str:
    try:
        source = str(text or "")
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        source = f"<unstringifiable:{type(exc).__name__}>"
    return hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()


def stable_json_text(value: Any) -> str:
    text, _diagnostic = safe_json_text(value, reason="stable_json_text_failed")
    return text


def stable_json_fingerprint(value: Any) -> tuple[int, str]:
    text = stable_json_text(value)
    return len(text), sha256_text(text)


def counted_list(value: Any, *, limit: int = 20) -> dict[str, Any]:
    if not isinstance(value, list):
        return {}
    try:
        shown = value[: max(0, int(limit or 0))]
    except (TypeError, ValueError) as exc:
        return diagnostic_row("counted_list_limit_invalid", exc=exc, limit=safe_text(limit, limit=100))
    return {
        "count": len(value),
        "items": shown,
        "omitted_count": max(0, len(value) - len(shown)),
    }


def _is_empty_value(value: Any) -> bool:
    try:
        return value in (None, "", [], {})
    except Exception:
        return False


def compact_value(
    value: Any,
    *,
    text_limit: int = 700,
    list_limit: int = 8,
    depth: int = 0,
    _seen: set[int] | None = None,
) -> Any:
    if depth > 4:
        return diagnostic_row("compact_value_depth_limit", value_preview=safe_text(value, limit=text_limit))
    if isinstance(value, str):
        return value[:text_limit]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if _seen is None:
        _seen = set()
    if isinstance(value, list):
        value_id = id(value)
        if value_id in _seen:
            return diagnostic_row("compact_value_cycle_detected", value_type="list")
        _seen.add(value_id)
        try:
            shown = value[: max(0, int(list_limit or 0))]
        except (TypeError, ValueError) as exc:
            return diagnostic_row("compact_value_list_limit_invalid", exc=exc)
        out = []
        for index, item in enumerate(shown):
            try:
                out.append(
                    compact_value(
                        item,
                        text_limit=text_limit,
                        list_limit=list_limit,
                        depth=depth + 1,
                        _seen=_seen,
                    )
                )
            except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                out.append(diagnostic_row("compact_value_list_item_failed", exc=exc, item_index=index))
        if len(value) > list_limit:
            out.append({"omitted_count": len(value) - list_limit})
        _seen.discard(value_id)
        return out
    if isinstance(value, dict):
        value_id = id(value)
        if value_id in _seen:
            return diagnostic_row("compact_value_cycle_detected", value_type="dict")
        _seen.add(value_id)
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_empty_value(item):
                continue
            key_text = safe_text(key, limit=120)
            try:
                out[key_text] = compact_value(
                    item,
                    text_limit=text_limit,
                    list_limit=list_limit,
                    depth=depth + 1,
                    _seen=_seen,
                )
            except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                out[key_text] = diagnostic_row("compact_value_dict_item_failed", exc=exc)
        _seen.discard(value_id)
        return out
    return safe_text(value, limit=text_limit)
