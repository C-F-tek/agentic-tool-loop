"""
aicarmine_broker.job_store
==========================
All persistence logic for agent jobs:
- SQLite initialisation and upserts
- Filesystem JSON state files
- NDJSON event log
- Job listing / loading helpers

Nothing in this module makes HTTP calls or runs subprocesses.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .config import *
from .application.public_payload.history_ledger import *
from .application.job.response_values import *
from .application.job.terminal_response import *
from .application.job.status_response import *
from .application.job.wait_response import *
from .infrastructure.json_files import *
from .infrastructure.job_sqlite_store import *
from .infrastructure.time_provider import *


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def now() -> int:
    return TimeProvider().now_seconds()


def make_session_id(value: str = "") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    if cleaned:
        return cleaned[:120]
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def write_json(path: Path, payload: Any) -> str:
    return str(JsonFileStore().write(path, payload))


def read_json(path: Path, default: Any = None) -> Any:
    return JsonFileStore().read(path, default)


def _job_sqlite_store() -> AgentJobSQLiteStore:
    return AgentJobSQLiteStore(AGENT_JOB_DB, AGENT_JOB_ROOT)


def _sqlite_error_category(exc: Exception) -> str:
    text = str(exc or "").lower()
    error_type = type(exc).__name__.lower()
    if "no such table" in text or "no such column" in text or "schema" in text:
        return "schema"
    if "readonly" in text or "read-only" in text or "attempt to write a readonly database" in text:
        return "readonly"
    if "permission denied" in text or "access is denied" in text or "operation not permitted" in text:
        return "permission"
    if "database is locked" in text or "database table is locked" in text or "locked" in text:
        return "locked"
    if isinstance(exc, sqlite3.IntegrityError) or "integrity" in error_type or "constraint" in text:
        return "integrity"
    if (
        "unable to open database file" in text
        or "not a database" in text
        or "file is not a database" in text
        or "database disk image is malformed" in text
    ):
        return "configuration"
    return "runtime"


def _sqlite_operator_hint(category: str) -> str:
    return {
        "schema": "SQLite schema missing or incompatible; verify DB initialization and broker version.",
        "permission": "SQLite path is not writable by the broker process; verify filesystem permissions.",
        "readonly": "SQLite database opened read-only; verify volume mount and file attributes.",
        "locked": "SQLite database is locked; verify concurrent writers or stale process state.",
        "integrity": "SQLite constraint/integrity failure; compare filesystem job state with SQLite index.",
        "configuration": "SQLite path or database file is invalid; verify AGENT_JOB_DB and parent directory.",
        "runtime": "SQLite secondary index failed at runtime; filesystem job state remains primary evidence.",
    }.get(category, "SQLite secondary index failed; inspect filesystem job state and broker logs.")


def _sqlite_warning(exc: Exception, *, filesystem_state_written: bool = True) -> dict[str, Any]:
    category = _sqlite_error_category(exc)
    return {
        "sqlite_write_failed": True,
        "sqlite_error_type": type(exc).__name__,
        "sqlite_error_category": category,
        "sqlite_error": str(exc)[:1000],
        "sqlite_db_path": str(AGENT_JOB_DB),
        "agent_job_root": str(AGENT_JOB_ROOT),
        "filesystem_state_written": filesystem_state_written,
        "sqlite_is_secondary_index": True,
        "sqlite_required": True,
        "sqlite_failure_requires_investigation": True,
        "sqlite_configuration_issue": category in {"schema", "permission", "readonly", "configuration"},
        "operator_hint": _sqlite_operator_hint(category),
        "ts": time.time(),
    }


def _log_sqlite_warning(job_id: str, operation: str, warning: dict[str, Any], exc: Exception) -> None:
    if not bool(warning.get("filesystem_state_written") or warning.get("filesystem_event_written")):
        return
    logger.warning(
        "SQLite secondary index write failed; operation=%s job_id=%s category=%s db=%s fs_fallback=%s error_type=%s error=%s",
        operation,
        job_id,
        warning.get("sqlite_error_category"),
        warning.get("sqlite_db_path"),
        bool(warning.get("filesystem_state_written") or warning.get("filesystem_event_written")),
        type(exc).__name__,
        str(exc)[:500],
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def session_root(session_id: str) -> Path:
    # Late import to avoid circular; workspace injected via _resolve_workspace()
    from .config import WORKSPACE  

    root = WORKSPACE / "sessions" / make_session_id(session_id)
    for name in ("commands", "reads", "tool-results", "artifacts"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def agent_job_root(job_id: str) -> Path:
    return AGENT_JOB_ROOT / make_session_id(job_id)


def agent_job_state_path(job_id: str) -> Path:
    return agent_job_root(job_id) / "job.json"


def agent_job_events_path(job_id: str) -> Path:
    return agent_job_root(job_id) / "events.ndjson"


def agent_job_planner_stream_dir(job_id: str) -> Path:
    path = agent_job_root(job_id) / "planner-stream"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_job_planner_stream_path(
    job_id: str, step: int, suffix: str = ""
) -> Path:
    extra = f"-{suffix}" if suffix else ""
    return (
        agent_job_planner_stream_dir(job_id) / f"step-{int(step):03d}{extra}.txt"
    )


def job_url(job_id: str) -> str:
    return f"{AGENT_PUBLIC_BASE_URL.rstrip('/')}/jobs/{job_id}"


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def init_agent_job_db() -> None:
    _job_sqlite_store().init()


# ---------------------------------------------------------------------------
# State read / write
# ---------------------------------------------------------------------------


def write_agent_job_state(state: dict[str, Any]) -> None:
    job_id = str(state["job_id"])
    root = agent_job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)
    state["workspace"] = str(root)
    state["updated_at"] = time.time()
    write_json(agent_job_state_path(job_id), state)
    try:
        _job_sqlite_store().upsert_job_state(state, root)
    except Exception as exc:
        warning = _sqlite_warning(exc)
        _log_sqlite_warning(job_id, "job_state_upsert", warning, exc)
        state["_persistence_warning"] = warning
        write_json(agent_job_state_path(job_id), state)
        append_agent_event_filesystem_only(
            job_id,
            "sqlite_write_failed",
            "Filesystem job state was written but SQLite index update failed.",
            warning,
            step=None,
        )


def load_agent_job_state(job_id: str) -> dict[str, Any]:
    state = read_json(agent_job_state_path(job_id), {})
    return state if isinstance(state, dict) else {}


def _job_list_row_from_state(
    state: dict[str, Any],
    *,
    index_source: str,
    sqlite_index_present: bool = False,
    sqlite_index_missing: bool = False,
    sqlite_index_error: str = "",
) -> dict[str, Any]:
    row = {
        "job_id": str(state.get("job_id") or ""),
        "status": str(state.get("status") or "unknown"),
        "goal": str(state.get("goal") or ""),
        "created_at": float(state.get("created_at") or state.get("updated_at") or 0),
        "updated_at": float(state.get("updated_at") or state.get("created_at") or 0),
        "workspace": str(state.get("workspace") or ""),
        "final_path": str(state.get("final_path") or ""),
        "error": str(state.get("error") or ""),
        "index_source": index_source,
    }
    if sqlite_index_present:
        row["sqlite_index_present"] = True
    if sqlite_index_missing:
        row["sqlite_index_missing"] = True
    if sqlite_index_error:
        row["sqlite_index_error"] = sqlite_index_error[:1000]
        row["sqlite_failure_requires_investigation"] = True
    if isinstance(state.get("_persistence_warning"), dict):
        row["_persistence_warning"] = state["_persistence_warning"]
    return row


def _list_agent_jobs_from_filesystem(limit: int = 50) -> list[dict[str, Any]]:
    if not AGENT_JOB_ROOT.exists():
        return []
    rows: list[dict[str, Any]] = []
    for child in AGENT_JOB_ROOT.iterdir():
        if not child.is_dir():
            continue
        state = read_json(child / "job.json", {})
        if not isinstance(state, dict) or not state.get("job_id"):
            continue
        rows.append(_job_list_row_from_state(state, index_source="filesystem"))
    rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
    return rows[: max(1, limit)]


def _merge_sqlite_and_filesystem_job_rows(
    sqlite_rows: list[dict[str, Any]],
    filesystem_rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    sqlite_by_id = {str(row.get("job_id") or ""): row for row in sqlite_rows if row.get("job_id")}
    filesystem_by_id = {str(row.get("job_id") or ""): row for row in filesystem_rows if row.get("job_id")}
    merged: list[dict[str, Any]] = []
    for job_id, fs_row in filesystem_by_id.items():
        fs_row = dict(fs_row)
        if job_id in sqlite_by_id:
            fs_row["index_source"] = "mixed"
            fs_row["sqlite_index_present"] = True
        else:
            fs_row["index_source"] = "filesystem_fallback"
            fs_row["sqlite_index_missing"] = True
        merged.append(fs_row)
    for job_id, sqlite_row in sqlite_by_id.items():
        if job_id in filesystem_by_id:
            continue
        row = dict(sqlite_row)
        row["index_source"] = "sqlite_only"
        row["filesystem_state_missing"] = True
        merged.append(row)
    merged.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
    return merged[: max(1, limit)]


def list_agent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    try:
        sqlite_rows = _job_sqlite_store().list_jobs(limit)
    except Exception as exc:
        error = str(exc)[:1000]
        rows = _list_agent_jobs_from_filesystem(limit)
        for row in rows:
            row["index_source"] = "filesystem_fallback"
            row["sqlite_index_error"] = error
            row["sqlite_failure_requires_investigation"] = True
        return rows
    filesystem_rows = _list_agent_jobs_from_filesystem(limit)
    return _merge_sqlite_and_filesystem_job_rows(sqlite_rows, filesystem_rows, limit)




# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def append_agent_event(
    job_id: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    step: int | None = None,
) -> None:
    event: dict[str, Any] = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "job_id": job_id,
        "step": step,
        "event_type": event_type,
        "message": message,
        "payload": payload or {},
    }
    root = agent_job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)
    with agent_job_events_path(job_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    try:
        _job_sqlite_store().append_event(event)
    except Exception as exc:
        warning = _sqlite_warning(exc)
        warning["filesystem_event_written"] = True
        warning["event_type"] = event_type
        _log_sqlite_warning(job_id, "event_append", warning, exc)
        append_agent_event_filesystem_only(
            job_id,
            "sqlite_event_write_failed",
            "Filesystem event was written but SQLite event index update failed.",
            warning,
            step=step,
        )


def append_agent_event_filesystem_only(
    job_id: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    step: int | None = None,
) -> None:
    event: dict[str, Any] = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "job_id": job_id,
        "step": step,
        "event_type": event_type,
        "message": message,
        "payload": payload or {},
        "event_storage": "filesystem_only",
    }
    root = agent_job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)
    with agent_job_events_path(job_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def read_agent_events(
    job_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    path = agent_job_events_path(job_id)
    if not path.exists():
        return []
    rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    for raw in rows[-max(1, limit) :]:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                events.append(decoded)
        except Exception:
            events.append({"event_type": "raw", "message": raw})
    return events


# ---------------------------------------------------------------------------
# Compact status helpers
# ---------------------------------------------------------------------------


def public_result_digest(result: Any) -> dict[str, Any]:
    return build_public_result_digest(result, AGENT_PUBLIC_RESULT_INLINE_CHARS)


def compact_agent_terminal_response(job_id: str, *, audience: str = "operator") -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return build_missing_job_response(job_id)

    job_root = agent_job_root(job_id)

    def repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if not isinstance(item, dict):
            return "", {"source": "missing"}
        for key in ("content", "full_content", "content_view"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value, {"source": f"state.{key}"}
        artifact = str(item.get("artifact") or "")
        if artifact:
            try:
                artifact_path = Path(artifact)
                if not artifact_path.is_absolute():
                    artifact_path = job_root / artifact_path
                resolved_artifact = artifact_path.resolve()
                resolved_root = job_root.resolve()
                if str(resolved_artifact).lower().startswith(str(resolved_root).lower()):
                    loaded = read_json(resolved_artifact, {})
                    if (
                        isinstance(loaded, dict)
                        and str(loaded.get("path") or item.get("path") or "")
                        == str(item.get("path") or loaded.get("path") or "")
                    ):
                        for key in ("content", "full_content", "content_view"):
                            value = loaded.get(key)
                            if isinstance(value, str) and value:
                                return value, {"source": f"artifact.{key}"}
            except Exception:
                return "", {"source": "artifact_read_failed"}
        return "", {"source": "missing"}

    def same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict) or not result.get("ok"):
            return result if isinstance(result, dict) else {}
        artifact = str(result.get("artifact") or "")
        if not artifact:
            return result
        try:
            artifact_path = Path(artifact)
            if not artifact_path.is_absolute():
                artifact_path = job_root / artifact_path
            resolved_artifact = artifact_path.resolve()
            resolved_root = job_root.resolve()
            if not str(resolved_artifact).lower().startswith(str(resolved_root).lower()):
                return result
            loaded = read_json(resolved_artifact, {})
        except Exception:
            return result
        if not isinstance(loaded, dict):
            return result
        expected_tool = str(result.get("tool") or "")
        loaded_tool = str(loaded.get("tool") or "")
        if expected_tool and loaded_tool and expected_tool != loaded_tool:
            return result
        return loaded

    final_path = str(state.get("final_path") or "")
    final_data: dict[str, Any] = {}
    if final_path:
        loaded_final = read_json(Path(final_path), {})
        if isinstance(loaded_final, dict):
            final_data = loaded_final
    return build_compact_terminal_response(
        job_id=job_id,
        state=state,
        final_data=final_data,
        events_tail=read_agent_events(job_id, 20),
        events_path=str(agent_job_events_path(job_id)),
        job_url_value=job_url(job_id),
        public_result_inline_chars=AGENT_PUBLIC_RESULT_INLINE_CHARS,
        public_summary_chars=AGENT_PUBLIC_SUMMARY_CHARS,
        public_answer_chars=AGENT_PUBLIC_ANSWER_CHARS,
        audience=audience,
        repo_read_item_full_content=repo_read_item_full_content,
        same_tool_artifact_payload=same_tool_artifact_payload,
        job_root=job_root,
    )


def compact_agent_status(
    job_id: str, include_events: bool = True
) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return build_missing_job_response(job_id)
    events = (
        read_agent_events(job_id, AGENT_JOB_MAX_INLINE_EVENTS)
        if include_events
        else []
    )
    return build_compact_status_response(
        job_id=job_id,
        state=state,
        events=events,
        job_url_value=job_url(job_id),
    )


def wait_for_agent_terminal(
    job_id: str, timeout_seconds: int
) -> dict[str, Any]:
    deadline = time.time() + max(1, int(timeout_seconds or 900))
    last_status: dict[str, Any] = {}
    while time.time() < deadline:
        last_status = compact_agent_status(job_id, include_events=False)
        if str(last_status.get("status") or "") in AGENT_TERMINAL_STATUSES:
            terminal = compact_agent_terminal_response(job_id, audience="openwebui")
            terminal["wait_completed"] = True
            if not terminal.get("evidence_guide_for_30b"):
                terminal["evidence_guide_for_30b"] = (
                    f"Agent job {job_id} reached terminal status={terminal.get('status')}. "
                    "Use inline tool_context_for_30b and priority payload fields."
                )
            return terminal
        time.sleep(AGENT_WAIT_POLL_SECONDS)
    last_status = compact_agent_status(job_id, include_events=False)
    return build_wait_timeout_response(
        job_id=job_id,
        last_status=last_status,
        timeout_seconds=timeout_seconds,
        events_tail=read_agent_events(job_id, 5),
    )

