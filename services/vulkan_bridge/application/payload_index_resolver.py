"""Resolve public payload index locations against inline JSON payloads."""

from __future__ import annotations

import json
import re
from typing import Any


SCHEMA = "payload_index_resolution.v1"

_TOKEN_RE = re.compile(r"^(?P<name>[^\[\]]+)(?:\[(?P<index>\d+|\*)\])?$")


def _parse_tool_context(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return value
    return parsed if isinstance(parsed, dict) else value


def _payload_for_resolution(payload: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(payload)
    if "tool_context_for_30b" in resolved:
        resolved["tool_context_for_30b"] = _parse_tool_context(resolved.get("tool_context_for_30b"))
    return resolved


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _tokenize(path: str) -> list[tuple[str, str | None]]:
    tokens: list[tuple[str, str | None]] = []
    for raw in str(path or "").split("."):
        raw = raw.strip()
        if not raw:
            continue
        match = _TOKEN_RE.match(raw)
        if not match:
            tokens.append((raw, None))
            continue
        tokens.append((match.group("name"), match.group("index")))
    return tokens


def _resolve_tokens(current: Any, tokens: list[tuple[str, str | None]]) -> list[Any]:
    if not tokens:
        return [current]
    name, index = tokens[0]
    rest = tokens[1:]
    if not isinstance(current, dict) or name not in current:
        return []
    value = current.get(name)
    if index is None:
        return _resolve_tokens(value, rest)
    if not isinstance(value, list):
        return []
    if index == "*":
        out: list[Any] = []
        for item in value:
            out.extend(_resolve_tokens(item, rest))
        return out
    try:
        item_index = int(index)
    except ValueError:
        return []
    if item_index < 0 or item_index >= len(value):
        return []
    return _resolve_tokens(value[item_index], rest)


def resolve_field_path(payload: dict[str, Any], path: str) -> dict[str, Any]:
    """Resolve one payload field path and report missing/empty targets."""

    normalized = _payload_for_resolution(payload)
    values = _resolve_tokens(normalized, _tokenize(path))
    non_empty = [value for value in values if not _is_empty(value)]
    return {
        "path": path,
        "exists": bool(values),
        "non_empty": bool(non_empty),
        "match_count": len(values),
    }


def _iter_location_values(value: Any):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_location_values(item)


def _iter_index_targets(payload_index: dict[str, Any]):
    for section in ("concrete_results", "partial_results"):
        rows = payload_index.get(section)
        if not isinstance(rows, list):
            continue
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for key in ("primary_location", "full_context_location", "field"):
                for location in _iter_location_values(row.get(key)):
                    if location:
                        yield section, row_index, key, location


def resolve_payload_index(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve concrete/partial payload index targets against the public payload."""

    payload_index = payload.get("payload_index_for_30b")
    if not isinstance(payload_index, dict):
        return {
            "schema": SCHEMA,
            "ok": True,
            "resolved": [],
            "unresolved": [],
            "empty_targets": [],
            "target_count": 0,
        }
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    empty_targets: list[dict[str, Any]] = []
    for section, row_index, key, location in _iter_index_targets(payload_index):
        result = resolve_field_path(payload, location)
        record = {
            "section": section,
            "row_index": row_index,
            "key": key,
            "path": location,
        }
        if not result["exists"]:
            unresolved.append({**record, "reason": "missing_target"})
        elif not result["non_empty"]:
            empty_targets.append({**record, "reason": "empty_target"})
        else:
            resolved.append({**record, "match_count": result["match_count"]})
    return {
        "schema": SCHEMA,
        "ok": not unresolved and not empty_targets,
        "resolved": resolved,
        "unresolved": unresolved,
        "empty_targets": empty_targets,
        "target_count": len(resolved) + len(unresolved) + len(empty_targets),
    }
