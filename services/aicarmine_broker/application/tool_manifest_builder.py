"""Planner tool manifest compaction and native schema helpers."""
from __future__ import annotations

import copy
from typing import Any

from .prompt_values import prompt_clip_text


def json_char_len(value: Any) -> int:
    try:
        import json

        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def compact_tool_manifest_for_prompt(tool_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for tool in tool_manifest:
        params = tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {}
        properties = params.get("properties") if isinstance(params.get("properties"), dict) else {}
        argument_contract = tool.get("argument_contract") if isinstance(tool.get("argument_contract"), dict) else {}
        description_limit = 700 if argument_contract else 180
        row: dict[str, Any] = {
            "name": tool.get("name"),
            "description": prompt_clip_text(tool.get("description"), description_limit),
            "required": params.get("required") if isinstance(params.get("required"), list) else [],
            "properties": list(properties.keys()),
        }
        any_of = params.get("anyOf") if isinstance(params.get("anyOf"), list) else []
        if any_of:
            row["schema_any_of"] = any_of
        if argument_contract:
            row["argument_contract"] = argument_contract
        compacted.append(row)
    return compacted


def tool_schema_name(item: dict[str, Any]) -> str:
    function = item.get("function") if isinstance(item, dict) else {}
    return str(function.get("name") or "").strip() if isinstance(function, dict) else ""


def filter_tool_manifest_for_names(
    tool_manifest: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    allowed = {str(name) for name in allowed_names if str(name).strip()}
    if not allowed:
        return []
    return [
        item
        for item in tool_manifest
        if str(item.get("name") or "") in allowed
    ]


def native_tools_schema_for_planner(
    tools_schema: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Return the provider-native Ollama schema for this turn."""
    filter_enabled = allowed_names is not None
    allowed = {str(name) for name in allowed_names or [] if str(name).strip()}
    native_schema: list[dict[str, Any]] = []
    for source_item in tools_schema:
        name = tool_schema_name(source_item)
        if filter_enabled and name not in allowed:
            continue
        item = copy.deepcopy(source_item)
        function = item.get("function") if isinstance(item, dict) else {}
        if not isinstance(function, dict):
            continue
        function.pop("argument_contract", None)
        function["description"] = prompt_clip_text(function.get("description"), 420)
        native_schema.append(item)
    return native_schema
