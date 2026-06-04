from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aicarmine_broker.domain import AgentJobSnapshot


class JobStoreRepository:
    """Adapter over the legacy job_store module."""

    def load(self, job_id: str) -> AgentJobSnapshot:
        from aicarmine_broker import job_store

        state = job_store.load_agent_job_state(job_id)
        workspace = Path(str(state.get("workspace") or job_store.agent_job_root(job_id)))
        history = tuple(state.get("history") or ())
        return AgentJobSnapshot(
            job_id=job_id,
            status=str(state.get("status") or "unknown"),
            goal=str(state.get("goal") or ""),
            workspace=workspace,
            history=history,
            state=state,
        )

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        from aicarmine_broker import job_store

        job_store.append_agent_event(
            job_id,
            step=None,
            event_type=event_type,
            message=str(payload.get("message") or event_type),
            payload=dict(payload),
        )

    def finalize(
        self,
        job_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> None:
        from aicarmine_broker import job_store

        state = job_store.load_agent_job_state(job_id)
        state.update(dict(payload))
        state["job_id"] = job_id
        state["status"] = status
        job_store.write_agent_job_state(state)
