"""Final quality route for planner decision validation."""

from __future__ import annotations

from typing import Any


def _apply_final_quality_route(
    decision: dict[str, Any],
    evidence: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """No-op final quality gate. Returns decision unchanged."""
    return decision