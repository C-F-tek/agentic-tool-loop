"""Tool usage telemetry for effective use optimization."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import SAFETY_FLAGS


def event(tool: str, action: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "tool": tool,
        "action": action,
        "passed": passed,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_tool_telemetry(events: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in events if not item["passed"]]
    tools = sorted({str(item["tool"]) for item in events})
    report = {
        "kind": "full0to10_effective_use_tool_telemetry",
        "passed": not failed,
        "tool_count": len(tools),
        "event_count": len(events),
        "tools": tools,
        "events": events,
        "errors": [f"{item['tool']}:{item['action']}" for item in failed],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    return report
