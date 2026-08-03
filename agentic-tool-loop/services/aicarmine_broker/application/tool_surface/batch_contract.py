"""Shared helpers for native read-only tool batch contracts."""
from __future__ import annotations

from typing import Any, Mapping

from ..shared.diagnostics import diagnostic_row, safe_json_text, safe_text


def canonical_batch_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 8:
        return safe_text(value, limit=300)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        try:
            pairs = sorted(value.items(), key=lambda pair: safe_text(pair[0], limit=120))
        except Exception as exc:
            return diagnostic_row("canonical_batch_mapping_failed", exc=exc)
        for key, item in pairs:
            try:
                canonical = canonical_batch_value(item, _depth=_depth + 1)
                if canonical in (None, "", [], {}):
                    continue
                out[safe_text(key, limit=120)] = canonical
            except Exception as exc:
                out[safe_text(key, limit=120)] = diagnostic_row("canonical_batch_value_failed", exc=exc)
        return out
    if isinstance(value, (list, tuple)):
        out: list[Any] = []
        for index, item in enumerate(value):
            try:
                canonical = canonical_batch_value(item, _depth=_depth + 1)
                if canonical in (None, "", [], {}):
                    continue
                out.append(canonical)
            except Exception as exc:
                out.append(diagnostic_row("canonical_batch_list_item_failed", exc=exc, item_index=index))
        return out
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        return text
    return value


def canonical_batch_arguments(args: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    source = dict(args) if isinstance(args, Mapping) else {}
    for key, value in source.items():
        canonical = canonical_batch_value(value)
        if canonical in (None, "", [], {}):
            continue
        out[str(key)] = canonical
    return out


def canonical_batch_args(args: Mapping[str, Any]) -> str:
    text, _diagnostic = safe_json_text(
        canonical_batch_arguments(args),
        reason="canonical_batch_args_json_failed",
        separators=(",", ":"),
    )
    return text


def canonical_batch_call_key(tool: str, args: Mapping[str, Any]) -> str:
    text, _diagnostic = safe_json_text(
        {
            "tool": safe_text(tool, limit=160).strip(),
            "arguments": canonical_batch_arguments(args),
        },
        reason="canonical_batch_call_key_json_failed",
        separators=(",", ":"),
    )
    return text
