"""SQLite primitives for 3572 job metadata and events."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def _error_preview(exc: Exception) -> str:
    return str(exc)[:500]


def _payload_json(payload: Any) -> str:
    try:
        return json.dumps(payload or {}, ensure_ascii=False, default=str)
    except (TypeError, ValueError, RecursionError) as exc:
        diagnostic = {
            "schema": "job_sqlite_payload_diagnostic.v1",
            "diagnostic_only": True,
            "reason": "payload_json_serialization_failed",
            "error_type": type(exc).__name__,
            "error": _error_preview(exc),
            "payload_type": type(payload).__name__,
        }
        return json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)


class AgentJobSQLiteStore:
    """Persist job index rows and event rows in the broker SQLite DB."""

    def __init__(self, db_path: Path, job_root: Path) -> None:
        self.db_path = Path(db_path)
        self.job_root = Path(job_root)

    def init(self) -> None:
        try:
            self.job_root.mkdir(parents=True, exist_ok=True)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self.db_path)) as db:
                db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id     TEXT PRIMARY KEY,
                        status     TEXT NOT NULL,
                        goal       TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        workspace  TEXT NOT NULL,
                        final_path TEXT,
                        error      TEXT
                    )
                    """
                )
                db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id     TEXT NOT NULL,
                        ts         REAL NOT NULL,
                        step       INTEGER,
                        event_type TEXT NOT NULL,
                        message    TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
                db.commit()
        except PermissionError:
            logger.warning("Permission denied initializing job SQLite store. db_path=%s job_root=%s", self.db_path, self.job_root)
            raise
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error initializing job store. db_path=%s", self.db_path)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error initializing job store. db_path=%s", self.db_path)
            raise

    def upsert_job_state(self, state: dict[str, Any], workspace: Path) -> None:
        job_id = str(state["job_id"])
        self.init()
        try:
            with sqlite3.connect(str(self.db_path)) as db:
                db.execute(
                    """
                    INSERT INTO jobs(job_id, status, goal, created_at, updated_at,
                                     workspace, final_path, error)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        status     = excluded.status,
                        goal       = excluded.goal,
                        updated_at = excluded.updated_at,
                        workspace  = excluded.workspace,
                        final_path = excluded.final_path,
                        error      = excluded.error
                    """,
                    (
                        job_id,
                        str(state.get("status") or "unknown"),
                        str(state.get("goal") or ""),
                        float(state.get("created_at") or time.time()),
                        float(state.get("updated_at") or time.time()),
                        str(state.get("workspace") or workspace),
                        str(state.get("final_path") or ""),
                        str(state.get("error") or ""),
                    ),
                )
                db.commit()
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error upserting job state. job_id=%s db_path=%s", job_id, self.db_path)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error upserting job state. job_id=%s db_path=%s", job_id, self.db_path)
            raise

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        self.init()
        try:
            with sqlite3.connect(str(self.db_path)) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    """
                    SELECT job_id, status, goal, created_at, updated_at,
                           workspace, final_path, error
                    FROM jobs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error listing jobs. db_path=%s limit=%s", self.db_path, limit)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error listing jobs. db_path=%s limit=%s", self.db_path, limit)
            raise

    def append_event(self, event: dict[str, Any]) -> None:
        self.init()
        job_id = str(event.get("job_id") or "")
        try:
            with sqlite3.connect(str(self.db_path)) as db:
                db.execute(
                    """
                    INSERT INTO events(job_id, ts, step, event_type, message, payload_json)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        float(event["ts"]),
                        event.get("step"),
                        str(event.get("event_type") or ""),
                        str(event.get("message") or ""),
                        _payload_json(event.get("payload") or {}),
                    ),
                )
                db.commit()
        except sqlite3.OperationalError:
            logger.debug("SQLite operational error appending job event. job_id=%s db_path=%s", job_id, self.db_path)
            raise
        except sqlite3.DatabaseError:
            logger.warning("SQLite database error appending job event. job_id=%s db_path=%s", job_id, self.db_path)
            raise
