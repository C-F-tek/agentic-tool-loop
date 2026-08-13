from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from ..domain import AgentJobSnapshot


logger = logging.getLogger(__name__)


def _mapping_payload(payload: Mapping[str, Any], *, job_id: str, event_type: str = "") -> dict[str, Any]:
    try:
        return dict(payload)
    except Exception as exc:
        logger.warning(
            "Failed to materialize job repository payload. job_id=%s event_type=%s error_type=%s",
            job_id,
            event_type,
            type(exc).__name__,
        )
        return {
            "schema": "job_repository_payload_diagnostic.v1",
            "diagnostic_only": True,
            "reason": "payload_mapping_failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "payload_type": type(payload).__name__,
        }


class JobStoreRepository:
    """Adapter over the legacy job_store module."""

    def load(self, job_id: str) -> AgentJobSnapshot:
        from .. import job_store

        try:
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
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error loading job snapshot. job_id=%s", job_id)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error loading job snapshot. job_id=%s", job_id)
            raise
        except PermissionError:
            logger.warning("Permission denied loading job snapshot. job_id=%s", job_id)
            raise

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        from .. import job_store

        payload_dict = _mapping_payload(payload, job_id=job_id, event_type=event_type)
        try:
            job_store.append_agent_event(
                job_id,
                step=None,
                event_type=event_type,
                message=str(payload_dict.get("message") or event_type),
                payload=payload_dict,
            )
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error appending job event. job_id=%s event_type=%s", job_id, event_type)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error appending job event. job_id=%s event_type=%s", job_id, event_type)
            raise
        except PermissionError:
            logger.warning("Permission denied appending job event. job_id=%s event_type=%s", job_id, event_type)
            raise

    def finalize(
        self,
        job_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> None:
        from .. import job_store

        try:
            state = job_store.load_agent_job_state(job_id)
            state.update(_mapping_payload(payload, job_id=job_id))
            state["job_id"] = job_id
            state["status"] = status
            job_store.write_agent_job_state(state)
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error finalizing job. job_id=%s status=%s", job_id, status)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error finalizing job. job_id=%s status=%s", job_id, status)
            raise
        except PermissionError:
            logger.warning("Permission denied finalizing job. job_id=%s status=%s", job_id, status)
            raise
