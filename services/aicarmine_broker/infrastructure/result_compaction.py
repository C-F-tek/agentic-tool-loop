"""Generic text compaction primitives."""
from __future__ import annotations

import json
import logging
from typing import Any


logger = logging.getLogger(__name__)

_TRUNCATION_SUFFIX = "\n... <truncated>"


def _preview(value: Any, *, limit: int = 300) -> str:
    try:
        return str(value)[:limit]
    except Exception as exc:
        return f"<unstringifiable:{type(exc).__name__}>"


def _diagnostic_text(value: Any, exc: Exception) -> str:
    diagnostic = {
        "schema": "result_compaction_diagnostic.v1",
        "diagnostic_only": True,
        "reason": "json_serialization_failed",
        "error_type": type(exc).__name__,
        "error": _preview(exc),
        "value_type": type(value).__name__,
    }
    return json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)


def _clip(text: str, limit: int) -> str:
    try:
        bounded_limit = max(0, int(limit))
    except (TypeError, ValueError):
        logger.debug("Invalid compaction limit. limit=%s", _preview(limit))
        bounded_limit = 0
    if len(text) <= bounded_limit:
        return text
    if bounded_limit <= len(_TRUNCATION_SUFFIX):
        return text[:bounded_limit]
    return text[: bounded_limit - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def compact(value: Any, limit: int) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            logger.debug(
                "Result compaction JSON serialization failed. value_type=%s error_type=%s",
                type(value).__name__,
                type(exc).__name__,
            )
            text = _diagnostic_text(value, exc)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _clip(text, limit)
