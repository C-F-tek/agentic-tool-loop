from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aicarmine_broker.application.job.worker import AgentJobWorker


def _worker_fixture(
    tmp_path: Path,
    *,
    planner_enabled: bool = True,
    fallback_oneshot: bool = False,
    planner_runner=None,
    agent_runner=None,
    state: dict[str, Any] | None = None,
):
    job_id = "job-worker-test"
    state_store: dict[str, dict[str, Any]] = {
        job_id: dict(
            state
            or {
                "job_id": job_id,
                "status": "queued",
                "request_payload": {"arguments": {}},
            }
        )
    }
    writes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    planner_calls: list[str] = []
    agent_calls: list[dict[str, Any]] = []

    def load_state(load_job_id: str) -> dict[str, Any]:
        return dict(state_store.get(load_job_id) or {})

    def write_state(next_state: dict[str, Any]) -> None:
        stored = dict(next_state)
        state_store[str(stored["job_id"])] = stored
        writes.append(stored)

    def append_event(
        event_job_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        *,
        step: int | None = None,
    ) -> None:
        events.append(
            {
                "job_id": event_job_id,
                "event_type": event_type,
                "message": message,
                "payload": payload or {},
                "step": step,
            }
        )

    def agent_job_root(root_job_id: str) -> Path:
        root = tmp_path / root_job_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def write_json(path: Path, payload: Any) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def default_planner_runner(run_job_id: str) -> dict[str, Any]:
        planner_calls.append(run_job_id)
        return {"ok": True}

    def default_agent_runner(payload: dict[str, Any]) -> dict[str, Any]:
        agent_calls.append(dict(payload))
        return {
            "ok": True,
            "verdict": "OK",
            "internal_vulkan": {"tool_called_by_vulkan": "repo_read"},
            "artifacts": ["artifact"],
        }

    worker = AgentJobWorker(
        load_state=load_state,
        write_state=write_state,
        append_event=append_event,
        agent_job_root=agent_job_root,
        write_json=write_json,
        planner_runner=planner_runner or default_planner_runner,
        agent_runner=agent_runner or default_agent_runner,
        summary_from_result=lambda result: f"summary:{result.get('verdict')}",
        agentic_planner_enabled=planner_enabled,
        agentic_fallback_oneshot=fallback_oneshot,
    )
    return worker, job_id, state_store, writes, events, planner_calls, agent_calls


def test_job_worker_sets_running_and_invokes_planner(tmp_path: Path) -> None:
    worker, job_id, _state_store, writes, events, planner_calls, _agent_calls = (
        _worker_fixture(tmp_path, planner_enabled=True)
    )

    worker.run(job_id)

    assert writes[0]["status"] == "running"
    assert planner_calls == [job_id]
    assert events[0]["event_type"] == "job_started"


def test_job_worker_returns_when_state_missing(tmp_path: Path) -> None:
    worker, _job_id, _state_store, writes, events, planner_calls, _agent_calls = (
        _worker_fixture(tmp_path, planner_enabled=True)
    )

    worker.run("missing-job")

    assert writes == []
    assert events == []
    assert planner_calls == []


def test_job_worker_legacy_oneshot_writes_terminal_payload(tmp_path: Path) -> None:
    state = {
        "job_id": "job-worker-test",
        "status": "queued",
        "request_payload": {
            "action": "start",
            "job_id": "stale",
            "arguments": {"job_id": "stale", "action": "start", "keep": "value"},
        },
    }
    worker, job_id, state_store, writes, events, _planner_calls, agent_calls = (
        _worker_fixture(
            tmp_path,
            planner_enabled=False,
            fallback_oneshot=True,
            state=state,
        )
    )

    worker.run(job_id)

    assert agent_calls == [
        {
            "arguments": {"keep": "value"},
            "mode": "tool_helper",
            "session_id": job_id,
        }
    ]
    assert state_store[job_id]["status"] == "completed"
    assert state_store[job_id]["result_ok"] is True
    assert state_store[job_id]["result"]["internal_tool"] == "repo_read"
    assert (tmp_path / job_id / "final.json").exists()
    assert (tmp_path / job_id / "final.md").read_text(encoding="utf-8") == "summary:OK"
    assert writes[-1]["final_path"].endswith("final.json")
    assert events[-1]["event_type"] == "job_finished"


def test_job_worker_failure_writes_error_state(tmp_path: Path) -> None:
    def failing_planner(_job_id: str) -> dict[str, Any]:
        raise RuntimeError("planner boom")

    worker, job_id, state_store, writes, events, _planner_calls, _agent_calls = (
        _worker_fixture(
            tmp_path,
            planner_enabled=True,
            planner_runner=failing_planner,
        )
    )

    worker.run(job_id)

    assert state_store[job_id]["status"] == "failed"
    assert state_store[job_id]["final_path"].endswith("error.txt")
    assert "RuntimeError: planner boom" in state_store[job_id]["error"]
    assert (tmp_path / job_id / "error.txt").exists()
    assert writes[-1]["status"] == "failed"
    assert events[-1]["event_type"] == "job_failed"
    assert events[-1]["payload"] == {"error_type": "RuntimeError"}
