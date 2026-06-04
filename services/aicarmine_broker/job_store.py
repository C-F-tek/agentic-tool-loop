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
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import (
    AGENT_JOB_DB,
    AGENT_JOB_MAX_INLINE_EVENTS,
    AGENT_JOB_ROOT,
    AGENT_PUBLIC_BASE_URL,
    AGENT_PUBLIC_ANSWER_CHARS,
    AGENT_PUBLIC_RESULT_INLINE_CHARS,
    AGENT_PUBLIC_SUMMARY_CHARS,
    AGENT_TERMINAL_STATUSES,
    AGENT_WAIT_POLL_SECONDS,
)
from .application.public_history_ledger import build_public_result_digest
from .application.job_response_values import (
    compact_json,
    compact_text,
    event_digest,
)
from .application.job_terminal_response import (
    build_compact_terminal_response,
    build_missing_job_response,
)
from .application.job_status_response import build_compact_status_response
from .application.job_wait_response import build_wait_timeout_response
from .infrastructure.json_files import JsonFileStore
from .infrastructure.job_sqlite_store import AgentJobSQLiteStore
from .infrastructure.time_provider import TimeProvider


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


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def session_root(session_id: str) -> Path:
    # Late import to avoid circular; workspace injected via _resolve_workspace()
    from .config import WORKSPACE  # noqa: PLC0415

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
    except Exception:
        pass  # SQLite failure must not prevent filesystem state write


def load_agent_job_state(job_id: str) -> dict[str, Any]:
    state = read_json(agent_job_state_path(job_id), {})
    return state if isinstance(state, dict) else {}


def list_agent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return _job_sqlite_store().list_jobs(limit)


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
    except Exception:
        pass


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


def compact_agent_terminal_response(job_id: str) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return build_missing_job_response(job_id)

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
            terminal = compact_agent_terminal_response(job_id)
            terminal["mode"] = "agent_job_final_waited_compact"
            terminal["wait_completed"] = True
            if not terminal.get("message_for_30b"):
                terminal["message_for_30b"] = (
                    f"Agent job {job_id} reached terminal status={terminal.get('status')}. "
                    "Use summary_for_30b; full output is in final_path/final_markdown_path."
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
