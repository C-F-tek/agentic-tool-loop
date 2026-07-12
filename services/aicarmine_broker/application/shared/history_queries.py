"""Small planner history query helpers."""
from __future__ import annotations

from typing import Any


def history_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    if result:
        return result
    if item.get("tool"):
        return item
    return {}


def history_has_tool(history: list[dict[str, Any]], tool_name: str) -> bool:
    for item in history:
        if not isinstance(item, dict):
            continue
        for field in ("tool_result", "decision"):
            value = item.get(field)
            if isinstance(value, dict) and value.get("tool") == tool_name:
                return True
    return False


