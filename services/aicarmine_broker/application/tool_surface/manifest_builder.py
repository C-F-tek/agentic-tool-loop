"""Planner tool manifest compaction from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

and native schema helpers."""
from __future__ import annotations

import copy
from typing import Any

from ..prompt.values import prompt_clip_text
from ..shared.diagnostics import diagnostic_row, safe_json_text, safe_text


def json_char_len(value: Any) -> int:
    text, _diagnostic = safe_json_text(value, reason="json_char_len_failed", sort_keys=False)
    return len(text)


def compact_tool_manifest_for_prompt(tool_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    if not isinstance(tool_manifest, list):
        return [
            diagnostic_row(
                "tool_manifest_not_list",
                schema="tool_manifest_prompt_diagnostic.v1",
                received_type=type(tool_manifest).__name__,
            )
        ]
    for index, tool in enumerate(tool_manifest):
        if not isinstance(tool, dict):
            compacted.append(diagnostic_row(
                "tool_manifest_item_not_object",
                schema="tool_manifest_prompt_diagnostic.v1",
                item_index=index,
                received_type=type(tool).__name__,
            ))
            continue
        try:
            params = tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {}
            properties = params.get("properties") if isinstance(params.get("properties"), dict) else {}
            argument_contract = tool.get("argument_contract") if isinstance(tool.get("argument_contract"), dict) else {}
            description_limit = 700 if argument_contract else 180
            row: dict[str, Any] = {
                "name": safe_text(tool.get("name"), limit=160),
                "description": prompt_clip_text(tool.get("description"), description_limit),
                "required": params.get("required") if isinstance(params.get("required"), list) else [],
                "properties": [safe_text(key, limit=160) for key in properties.keys()],
            }
            any_of = params.get("anyOf") if isinstance(params.get("anyOf"), list) else []
            if any_of:
                row["schema_any_of"] = any_of
            if argument_contract:
                row["argument_contract"] = argument_contract
            compacted.append(row)
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            compacted.append(diagnostic_row(
                "tool_manifest_item_compaction_failed",
                schema="tool_manifest_prompt_diagnostic.v1",
                exc=exc,
                item_index=index,
            ))
    return compacted


def tool_schema_name(item: dict[str, Any]) -> str:
    function = item.get("function") if isinstance(item, dict) else {}
    return str(function.get("name") or "").strip() if isinstance(function, dict) else ""


def filter_tool_manifest_for_names(
    tool_manifest: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    allowed = {safe_text(name, limit=160) for name in allowed_names or [] if safe_text(name, limit=160).strip()}
    if not allowed:
        return []
    return [
        item
        for item in (tool_manifest if isinstance(tool_manifest, list) else [])
        if isinstance(item, dict) and safe_text(item.get("name"), limit=160) in allowed
    ]


def native_tools_schema_for_planner(
    tools_schema: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Return the provider-native Ollama schema for this turn."""
    filter_enabled = allowed_names is not None
    allowed = {str(name) for name in allowed_names or [] if str(name).strip()}
    native_schema: list[dict[str, Any]] = []
    for source_item in tools_schema if isinstance(tools_schema, list) else []:
        try:
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
        except Exception:
            continue
    return native_schema
