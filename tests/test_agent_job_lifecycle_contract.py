from __future__ import annotations

from pathlib import Path
from typing import Any

from aicarmine_broker.application.job.lifecycle import AgentJobLifecycle


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeThread:
    def __init__(
        self,
        *,
        target,
        args,
        daemon: bool,
        name: str,
        alive: bool = False,
    ) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.started = False
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self.started = True
        self._alive = True


def _lifecycle_fixture(tmp_path: Path):
    states: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    waits: list[tuple[str, int]] = []
    worker_calls: list[str] = []
    threads: dict[str, FakeThread] = {}
    init_calls: list[bool] = []

    def init_agent_job_db() -> None:
        init_calls.append(True)

    def make_session_id(value: str) -> str:
        return value

    def agent_job_root(job_id: str) -> Path:
        return tmp_path / job_id

    def write_state(state: dict[str, Any]) -> None:
        states.append(dict(state))

    def append_event(
        job_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        *,
        step: int | None = None,
    ) -> None:
        events.append(
            {
                "job_id": job_id,
                "event_type": event_type,
                "message": message,
                "payload": payload or {},
                "step": step,
            }
        )

    def job_url(job_id: str) -> str:
        return f"http://127.0.0.1:3572/jobs/{job_id}"

    def wait_for_terminal(job_id: str, wait_seconds: int) -> dict[str, Any]:
        waits.append((job_id, wait_seconds))
        return {"ok": True, "status": "completed"}

    def worker(job_id: str) -> None:
        worker_calls.append(job_id)

    def thread_factory(**kwargs) -> FakeThread:
        return FakeThread(**kwargs)

    lifecycle = AgentJobLifecycle(
        init_agent_job_db=init_agent_job_db,
        make_session_id=make_session_id,
        agent_job_root=agent_job_root,
        write_state=write_state,
        append_event=append_event,
        job_url=job_url,
        wait_for_terminal=wait_for_terminal,
        worker=worker,
        background_threads=threads,
        lock=FakeLock(),
        agent_default_max_steps=100,
        approval_mode="never",
        return_wait_seconds=12,
        agentic_planner_enabled=True,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="planner-model",
        selector_url="http://127.0.0.1:11435/api/chat",
        selector_model="selector-model",
        thread_factory=thread_factory,
        now=lambda: 10.0,
        uuid_token=lambda: "abcdef12",
    )
    return lifecycle, states, events, waits, worker_calls, threads, init_calls


def test_job_lifecycle_start_creates_queued_state(tmp_path: Path) -> None:
    lifecycle, states, events, waits, _worker_calls, threads, init_calls = (
        _lifecycle_fixture(tmp_path)
    )

    result = lifecycle.start(
        {"request": "analyze", "return_mode": "background"},
        "vulkan_helper",
        {"max_steps": 7, "approval_mode": "manual"},
        "Analyze repo",
    )

    assert init_calls == [True]
    assert states == [
        {
            "job_id": "job-abcdef12",
            "status": "queued",
            "goal": "Analyze repo",
            "public_tool_name": "vulkan_helper",
            "created_at": 10.0,
            "updated_at": 10.0,
            "workspace": str(tmp_path / "job-abcdef12"),
            "request_payload": {"request": "analyze", "return_mode": "background"},
            "original_args": {"max_steps": 7, "approval_mode": "manual"},
            "max_steps": 7,
            "approval_mode": "manual",
            "return_mode": "background",
            "agentic_planner_enabled": True,
            "planner_url": "http://127.0.0.1:11434/api/chat",
            "planner_model": "planner-model",
            "selector_url": "http://127.0.0.1:11435/api/chat",
            "selector_model": "selector-model",
        }
    ]
    assert events[0]["event_type"] == "job_queued"
    assert result["mode"] == "agent_job_started"
    assert result["job_id"] == "job-abcdef12"
    assert waits == []
    assert threads["job-abcdef12"].started is True
    assert threads["job-abcdef12"].name == "aicarmine-agent-job-job-abcdef12"


def test_job_lifecycle_wait_mode_adds_terminal_metadata(tmp_path: Path) -> None:
    lifecycle, _states, _events, waits, _worker_calls, _threads, _init_calls = (
        _lifecycle_fixture(tmp_path)
    )

    result = lifecycle.start(
        {"request": "analyze"},
        "vulkan_helper",
        {"wait_seconds": 5},
        "Analyze repo",
    )

    assert waits == [("job-abcdef12", 5)]
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["started_job"]["mode"] == "agent_job_started"
    assert result["tool_name"] == "vulkan_helper"
    assert result["called_by_30b"] == "vulkan_helper"
    assert result["job_url"] == "http://127.0.0.1:3572/jobs/job-abcdef12"


def test_job_lifecycle_reuses_alive_existing_thread(tmp_path: Path) -> None:
    lifecycle, _states, _events, _waits, _worker_calls, threads, _init_calls = (
        _lifecycle_fixture(tmp_path)
    )
    threads["fixed"] = FakeThread(
        target=lambda _job_id: None,
        args=("fixed",),
        daemon=True,
        name="existing",
        alive=True,
    )

    lifecycle.start(
        {"request": "analyze", "return_mode": "background"},
        "vulkan_helper",
        {"job_id": "fixed"},
        "Analyze repo",
    )

    assert threads["fixed"].name == "existing"
    assert threads["fixed"].started is False
