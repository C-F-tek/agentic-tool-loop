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
import sqlite3
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
from .infrastructure.json_files import JsonFileStore
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
    AGENT_JOB_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_JOB_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(AGENT_JOB_DB)) as db:
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
        init_agent_job_db()
        with sqlite3.connect(str(AGENT_JOB_DB)) as db:
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
                    str(state.get("workspace") or root),
                    str(state.get("final_path") or ""),
                    str(state.get("error") or ""),
                ),
            )
            db.commit()
    except Exception:
        pass  # SQLite failure must not prevent filesystem state write


def load_agent_job_state(job_id: str) -> dict[str, Any]:
    state = read_json(agent_job_state_path(job_id), {})
    return state if isinstance(state, dict) else {}


def list_agent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    init_agent_job_db()
    with sqlite3.connect(str(AGENT_JOB_DB)) as db:
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
        init_agent_job_db()
        with sqlite3.connect(str(AGENT_JOB_DB)) as db:
            db.execute(
                """
                INSERT INTO events(job_id, ts, step, event_type, message, payload_json)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    float(event["ts"]),
                    step,
                    event_type,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                ),
            )
            db.commit()
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


def compact_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if int(limit or 0) <= 0:
        return text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 40)] + "\n... <see final.md/final.json for full output>"


def compact_json(value: Any, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = str(value)
    return compact_text(text, limit)


def event_digest(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    digest: dict[str, Any] = {
        "time": event.get("time") or event.get("ts"),
        "step": event.get("step"),
        "event_type": event.get("event_type"),
        "message": event.get("message"),
    }
    if payload:
        digest["payload_keys"] = sorted(str(k) for k in payload.keys())[:20]
        for key in ("tool", "ok", "status", "path", "artifact", "returncode", "count", "truncated"):
            if key in payload:
                digest[key] = payload.get(key)
    return {k: v for k, v in digest.items() if v not in (None, "", [], {})}


def public_result_digest(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"preview": compact_json(result, AGENT_PUBLIC_RESULT_INLINE_CHARS)} if result else {}

    digest: dict[str, Any] = {}
    passthrough = (
        "ok", "status", "auto_finalized_by", "blocked_by", "rejected_tool",
        "blocked_tool", "error", "error_type", "planner_decision",
    )
    for key in passthrough:
        if key in result and key != "planner_decision":
            digest[key] = result.get(key)

    decision = result.get("planner_decision")
    if isinstance(decision, dict):
        digest["planner_decision"] = {
            k: decision.get(k)
            for k in ("action", "tool", "reason", "selected_by_3572", "coerced_by_3572")
            if decision.get(k) not in (None, "", [], {})
        }

    history = result.get("history")
    if isinstance(history, list):
        digest["history_count"] = len(history)
        tail: list[dict[str, Any]] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            d = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            r = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
            tail.append({
                k: v for k, v in {
                    "step": item.get("step"),
                    "action": d.get("action"),
                    "tool": r.get("tool") or d.get("tool"),
                    "ok": r.get("ok"),
                    "path": r.get("path"),
                    "artifact": r.get("artifact"),
                    "returncode": r.get("returncode"),
                    "truncated": r.get("truncated"),
                }.items() if v not in (None, "", [], {})
            })
        digest["history_tail"] = tail

    artifacts: list[str] = []
    for key in ("artifact", "backup_artifact"):
        value = result.get(key)
        if isinstance(value, str) and value and value not in artifacts:
            artifacts.append(value)
    for value in result.get("artifacts") or []:
        if isinstance(value, str) and value and value not in artifacts:
            artifacts.append(value)
    if artifacts:
        digest["artifacts"] = artifacts[:20]

    if not digest:
        digest["preview"] = compact_json(result, AGENT_PUBLIC_RESULT_INLINE_CHARS)
    return digest


def compact_agent_terminal_response(job_id: str) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {
            "ok": False,
            "service": "vulkan_agent",
            "tool_name": "vulkan_helper",
            "error": "job_not_found",
            "job_id": job_id,
        }

    status = str(state.get("status") or "unknown")
    public_tool = str(state.get("public_tool_name") or "vulkan_helper")
    final_path = str(state.get("final_path") or "")
    final_markdown_path = str(state.get("final_markdown_path") or "")
    events_path = str(agent_job_events_path(job_id))
    summary = compact_text(state.get("final_summary") or state.get("error") or "", AGENT_PUBLIC_SUMMARY_CHARS)
    events = [event_digest(ev) for ev in read_agent_events(job_id, 5)]

    artifacts = [p for p in (final_path, final_markdown_path, events_path) if p]
    result_digest = public_result_digest(state.get("result") or {})
    tool_context = state.get("tool_context_for_30b")
    final_data: dict[str, Any] = {}
    if final_path:
        loaded_final = read_json(Path(final_path), {})
        if isinstance(loaded_final, dict):
            final_data = loaded_final
    if not isinstance(tool_context, dict):
        for key in ("tool_context_for_30b", "agent_context_for_30b", "structured_context_for_30b", "structured_result_for_30b"):
            if isinstance(final_data.get(key), dict):
                tool_context = final_data.get(key)
                break
    answer = (
        state.get("answer_for_30b")
        or final_data.get("answer_for_30b")
        or (tool_context.get("answer_for_30b") if isinstance(tool_context, dict) else "")
        or summary
    )
    answer = compact_text(answer, AGENT_PUBLIC_ANSWER_CHARS)
    next_action = (
        state.get("next_action_for_30b")
        or final_data.get("next_action_for_30b")
        or (tool_context.get("next_action_for_30b") if isinstance(tool_context, dict) else {})
    )
    if not isinstance(next_action, dict):
        next_action = {}
    if not isinstance(tool_context, dict):
        tool_context = {
            "type": "agentic_loop_complete_structured_context_unavailable",
            "contract_type": "structured_agentic_loop_context_unavailable",
            "job": {"job_id": job_id, "status": status, "goal": state.get("goal")},
            "answer_for_30b": answer,
            "next_action_for_30b": next_action,
            "result": result_digest,
            "events_tail_digest": [event_digest(ev) for ev in read_agent_events(job_id, 20)],
        }

    context_alias = {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }
    return {
        "ok": True,
        "job_ok": status == "completed",
        "service": "vulkan_agent",
        "mode": "agent_job_final_compact",
        "tool_name": public_tool,
        "tool_result_for": public_tool,
        "called_by_30b": public_tool,
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "job_url": job_url(job_id),
        "final_path": final_path,
        "final_markdown_path": final_markdown_path,
        "events_path": events_path,
        "full_result_available": bool(final_path),
        "full_result_hint": "Open final_path/final_markdown_path or the job_url for the complete untruncated result.",
        "answer_for_30b": answer,
        "summary_for_30b": summary,
        "message_for_30b": answer,
        "evidence_digest_for_30b": (
            tool_context.get("evidence_digest_for_30b") if isinstance(tool_context, dict) else ""
        ),
        "final_summary": summary,
        "next_action_for_30b": next_action,
        "working_memory_for_30b": state.get("working_memory_for_30b") or final_data.get("working_memory_for_30b") or {},
        "evidence_contract": state.get("evidence_contract") or final_data.get("evidence_contract") or {},
        "planner_emission_interpreter": state.get("planner_emission_interpreter") or final_data.get("planner_emission_interpreter") or {},
        "openwebui_usage": {
            "primary_answer_field": "answer_for_30b",
            "structured_context_field": "tool_context_for_30b",
            "rule": "Answer the user from answer_for_30b; use structured context only for evidence-bound details.",
        },
        "result": result_digest,
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": context_alias,
        "structured_context_for_30b": context_alias,
        "structured_result_for_30b": context_alias,
        "artifacts": artifacts,
        "events_tail_digest": events,
    }


def compact_agent_status(
    job_id: str, include_events: bool = True
) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {
            "ok": False,
            "service": "vulkan_agent",
            "tool_name": "vulkan_helper",
            "error": "job_not_found",
            "job_id": job_id,
        }
    events = (
        read_agent_events(job_id, AGENT_JOB_MAX_INLINE_EVENTS)
        if include_events
        else []
    )
    memory = state.get("working_memory_for_30b") if isinstance(state.get("working_memory_for_30b"), dict) else {}
    evidence = state.get("evidence_contract") if isinstance(state.get("evidence_contract"), dict) else {}
    running_context = {
        "type": "agentic_loop_running_structured_context",
        "job": {
            "job_id": job_id,
            "status": state.get("status"),
            "goal": state.get("goal"),
            "current_step": state.get("current_step"),
            "status_message": state.get("status_message"),
        },
        "working_memory_for_30b": memory,
        "evidence_contract": evidence,
        "events_tail_digest": [event_digest(ev) for ev in events[-10:]],
    }
    message_for_30b = state.get("answer_for_30b") or (
        f"Agent job {job_id} status={state.get('status')} "
        f"step={state.get('current_step')} message={state.get('status_message') or ''}. "
        "Use working_memory_for_30b/evidence_contract from this same tool result before deciding the next call."
    )

    return {
        "ok": True,
        "service": "vulkan_agent",
        "mode": "agent_job_status",
        "tool_name": str(state.get("public_tool_name") or "vulkan_helper"),
        "tool_result_for": str(state.get("public_tool_name") or "vulkan_helper"),
        "called_by_30b": str(state.get("public_tool_name") or "vulkan_helper"),
        "job_id": job_id,
        "status": state.get("status"),
        "goal": state.get("goal"),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "workspace": state.get("workspace"),
        "job_url": job_url(job_id),
        "events_tail": events,
        "final_path": state.get("final_path"),
        "final_summary": state.get("final_summary", ""),
        "answer_for_30b": state.get("answer_for_30b", ""),
        "next_action_for_30b": state.get("next_action_for_30b", {}),
        "working_memory_for_30b": state.get("working_memory_for_30b", {}),
        "evidence_contract": state.get("evidence_contract", {}),
        "planner_emission_interpreter": state.get("planner_emission_interpreter", {}),
        "current_step": state.get("current_step"),
        "status_message": state.get("status_message", ""),
        "result": state.get("result", {}),
        "tool_context_for_30b": state.get("tool_context_for_30b") or running_context,
        "agent_context_for_30b": state.get("agent_context_for_30b") or running_context,
        "structured_context_for_30b": state.get("structured_context_for_30b") or running_context,
        "structured_result_for_30b": state.get("structured_result_for_30b") or running_context,
        "message_for_30b": message_for_30b,
        "answer_for_30b": state.get("answer_for_30b") or message_for_30b,
    }


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
    last_status["mode"] = "agent_job_wait_timeout"
    last_status["wait_completed"] = False
    last_status["wait_timeout_seconds"] = timeout_seconds
    last_status["events_tail_digest"] = [event_digest(ev) for ev in read_agent_events(job_id, 5)]
    memory = last_status.get("working_memory_for_30b") if isinstance(last_status.get("working_memory_for_30b"), dict) else {}
    candidates = memory.get("candidate_next_actions") if isinstance(memory.get("candidate_next_actions"), list) else []
    rejections = memory.get("rejections_tail") if isinstance(memory.get("rejections_tail"), list) else []
    last_status["message_for_30b"] = (
        f"Agent job {job_id} is still running after {timeout_seconds}s; "
        f"status={last_status.get('status')} step={last_status.get('current_step')} "
        f"message={last_status.get('status_message') or ''}. "
        f"candidate_next_actions={len(candidates)} recent_rejections={len(rejections)}. "
        "The structured working_memory_for_30b/evidence_contract fields are included in this same result; "
        "use them before deciding whether to call action='status' or action='result'."
    )
    last_status["answer_for_30b"] = last_status["message_for_30b"]
    last_status["next_action_for_30b"] = {
        "action": "continue_same_openwebui_context",
        "status": last_status.get("status"),
        "job_id": job_id,
        "tool_call": {
            "tool_name": "vulkan_helper",
            "arguments": {"action": "status", "job_id": job_id},
        },
        "do_not": [
            "do_not_drop_openwebui_context",
            "do_not_treat_dashboard_url_as_only_result",
            "do_not_start_duplicate_job_for_same_request",
        ],
    }
    last_status["continuation_surface"] = {
        "public_tool": "vulkan_helper",
        "current_call_wait_timed_out": True,
        "same_job_id": job_id,
        "call_protocol": {"action": "status", "job_id": job_id},
        "result_protocol": {"action": "result", "job_id": job_id},
    }
    return last_status
