from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class PlannerClient(Protocol):
    """Transport port for one 11434 planner turn."""

    def plan(
        self,
        job_id: str,
        turn_index: int,
        state: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Execute one planner turn and return the new state."""
