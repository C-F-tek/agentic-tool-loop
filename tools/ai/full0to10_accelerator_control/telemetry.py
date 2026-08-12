"""Telemetry for accelerator control plane."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import SAFETY_FLAGS


def telemetry_event(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": name,
        "passed": passed,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_accelerator_telemetry(events: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [event for event in events if not event["passed"]]
    report = {
        "kind": "full0to10_accelerator_telemetry",
        "passed": not failed,
        "event_count": len(events),
        "events": events,
        "errors": [event["event"] for event in failed],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    return report
