"""Telemetry for provider execution bridge."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import SAFETY_FLAGS


def event(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": name,
        "passed": passed,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_bridge_telemetry(events: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in events if not item["passed"]]
    report = {
        "kind": "full0to10_provider_execution_bridge_telemetry",
        "passed": not failed,
        "event_count": len(events),
        "events": events,
        "errors": [item["event"] for item in failed],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    return report
