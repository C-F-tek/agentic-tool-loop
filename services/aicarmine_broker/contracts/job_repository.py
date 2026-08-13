from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..domain import AgentJobSnapshot


class JobRepository(Protocol):
    """Persistence port for 3572 job state and terminal payloads.

    Defines the interface for loading job snapshots, appending typed events,
    and writing final terminal state to the broker's job storage backend.
    """

    def load(self, job_id: str) -> AgentJobSnapshot:
        """Load a stable job snapshot.

        Args:
            job_id: The unique identifier for the agent job.
        Returns:
            An AgentJobSnapshot containing the job's current state.
        """
        
    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Append a typed job event.

        Args:
            job_id: The unique identifier for the agent job.
            event_type: The category of event being recorded.
            payload: The structured data associated with the event.
        """

    def finalize(
        self,
        job_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Write terminal state and public payload data.

        Args:
            job_id: The unique identifier for the agent job.
            status: The final status string (e.g., 'completed', 'failed').
            payload: The terminal payload data to persist.
        """
