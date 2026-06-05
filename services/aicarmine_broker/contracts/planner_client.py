from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class PlannerClient(Protocol):
    """Transport port for one 11434 planner turn."""

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        options: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return the raw planner response for a measured prompt payload."""
