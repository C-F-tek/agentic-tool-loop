from __future__ import annotations

from typing import Any, Mapping, Protocol

from aicarmine_broker.domain import AgentJobSnapshot


class JobRepository(Protocol):
    """Persistence port for 3572 job state and terminal payloads."""

    def load(self, job_id: str) -> AgentJobSnapshot:
        """Load a stable job snapshot."""
        
    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Append a typed job event."""

    def finalize(
        self,
        job_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Write terminal state and public payload data."""
