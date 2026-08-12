"""Telemetry for provider governor."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import SAFETY_FLAGS


def event(
    name: str,
    passed: bool,
    details: dict[str, Any],
    *,
    severity: str = "info",
    structural: bool = False,
) -> dict[str, Any]:
    return {
        "event": name,
        "passed": passed,
        "severity": severity,
        "structural": structural,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_telemetry(events: list[dict[str, Any]]) -> dict[str, Any]:
    structural_failures = [
        item for item in events
        if item.get("structural") is True and item.get("passed") is not True
    ]
    policy_denials = [
        item for item in events
        if item.get("structural") is not True and item.get("passed") is not True
    ]
    report = {
        "kind": "full0to10_provider_governor_telemetry",
        "passed": not structural_failures,
        "event_count": len(events),
        "events": events,
        "structural_failure_count": len(structural_failures),
        "policy_denial_event_count": len(policy_denials),
        "errors": [item["event"] for item in structural_failures],
        "warnings": [item["event"] for item in policy_denials],
    }
    report.update(SAFETY_FLAGS)
    return report
