"""Shared helpers for native read-only tool batch contracts."""
from __future__ import annotations

import json
from typing import Any, Mapping


def canonical_batch_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            canonical = canonical_batch_value(item)
            if canonical in (None, "", [], {}):
                continue
            out[str(key)] = canonical
        return out
    if isinstance(value, (list, tuple)):
        out: list[Any] = []
        for item in value:
            canonical = canonical_batch_value(item)
            if canonical in (None, "", [], {}):
                continue
            out.append(canonical)
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
    return json.dumps(
        canonical_batch_arguments(args),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_batch_call_key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "tool": str(tool or "").strip(),
            "arguments": canonical_batch_arguments(args),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
