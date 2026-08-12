"""Lane role policy for AI workload quality validation."""
from __future__ import annotations

from typing import Any

from .constants import LANE_ROLES


def lane_role(lane: str) -> dict[str, Any]:
    return dict(
        LANE_ROLES.get(
            lane,
            {
                "provider": lane or "unknown",
                "compute_lane": "unknown",
                "allowed_role_when_usable": "context_only",
                "execution_mode": "explicit_only",
            },
        )
    )


def advisory_use(lane: str, usable: bool) -> dict[str, Any]:
    role = lane_role(lane)
    if not usable:
        return {
            "allowed_as_advisory_context": False,
            "allowed_role": "excluded_from_advisory_context",
            "reason": "unusable_workload_report",
        }
    if lane == "ollama":
        return {
            "allowed_as_advisory_context": True,
            "allowed_role": "primary_advisory",
            "reason": "usable_text_primary_advisory_lane",
        }
    if lane == "npu":
        return {
            "allowed_as_advisory_context": False,
            "allowed_role": role["allowed_role_when_usable"],
            "reason": "npu_is_not_primary_advisory_lane",
        }
    return {
        "allowed_as_advisory_context": True,
        "allowed_role": role["allowed_role_when_usable"],
        "reason": "usable_text_context_lane",
    }
