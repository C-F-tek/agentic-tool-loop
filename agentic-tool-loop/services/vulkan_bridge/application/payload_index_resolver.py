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


def _parse_tool_context_diagnostic(field: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return {
            "field": field,
            "reason": "invalid_json",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "value_preview": value[:500],
        }
    except (TypeError, ValueError) as exc:
        return {
            "field": field,
            "reason": "parse_error",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "value_preview": value[:500],
        }
    if not isinstance(parsed, dict):
        return {
            "field": field,
            "reason": "parsed_value_not_object",
            "decoded_type": type(parsed).__name__,
        }
    return {}


def _payload_for_resolution(payload: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(payload)
    if "tool_context" in resolved:
        resolved["tool_context"] = _parse_tool_context(resolved.get("tool_context"))
    return resolved


def _payload_for_resolution_with_diagnostics(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = dict(payload)
    diagnostics: list[dict[str, Any]] = []
    if "tool_context" in resolved:
        diagnostic = _parse_tool_context_diagnostic("tool_context", resolved.get("tool_context"))
        if diagnostic:
            diagnostics.append(diagnostic)
        resolved["tool_context"] = _parse_tool_context(resolved.get("tool_context"))
    return resolved, diagnostics


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _tokenize_with_diagnostics(path: str) -> tuple[list[tuple[str, str | None]], list[dict[str, Any]]]:
    tokens: list[tuple[str, str | None]] = []
    diagnostics: list[dict[str, Any]] = []
    for position, raw in enumerate(str(path or "").split(".")):
        raw = raw.strip()
        if not raw:
            continue
        match = _TOKEN_RE.match(raw)
        if not match:
            tokens.append((raw, None))
            diagnostics.append({
                "position": position,
                "token": raw,
                "reason": "invalid_token_syntax",
            })
            continue
        tokens.append((match.group("name"), match.group("index")))
    return tokens, diagnostics


def _tokenize(path: str) -> list[tuple[str, str | None]]:
    tokens, _diagnostics = _tokenize_with_diagnostics(path)
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

    normalized, parse_diagnostics = _payload_for_resolution_with_diagnostics(payload)
    tokens, token_diagnostics = _tokenize_with_diagnostics(path)
    values = _resolve_tokens(normalized, tokens)
    non_empty = [value for value in values if not _is_empty(value)]
    return {
        "path": path,
        "normalized_path": str(path or "").strip(),
        "exists": bool(values),
        "non_empty": bool(non_empty),
        "match_count": len(values),
        "token_count": len(tokens),
        "tokenization_errors": token_diagnostics,
        "parse_diagnostics": parse_diagnostics,
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

    payload_index = payload.get("payload_index")
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
            unresolved.append({
                **record,
                "reason": "missing_target",
                "tokenization_errors": result.get("tokenization_errors") or [],
                "parse_diagnostics": result.get("parse_diagnostics") or [],
            })
        elif not result["non_empty"]:
            empty_targets.append({
                **record,
                "reason": "empty_target",
                "match_count": result["match_count"],
                "parse_diagnostics": result.get("parse_diagnostics") or [],
            })
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
