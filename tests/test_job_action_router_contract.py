from __future__ import annotations

from pathlib import Path
from typing import Any

from aicarmine_broker.application.job_action_router import AgentJobActionRouter


class FakeSelectorRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "mode": "selector", "task": kwargs["task"]}


def _router_fixture(tmp_path: Path):
    calls: dict[str, Any] = {
        "start": [],
        "status": [],
        "result": [],
        "writes": [],
        "events": [],
    }
    states: dict[str, dict[str, Any]] = {
        "job-1": {"job_id": "job-1", "status": "running"}
    }
    selector = FakeSelectorRunner()

    def public_tool(payload: dict[str, Any]) -> str:
        return str(payload.get("tool") or "vulkan_helper")

    def public_args(payload: dict[str, Any]) -> dict[str, Any]:
        return dict(payload.get("arguments") or {})

    def make_session_id(value: str) -> str:
        return value or "session"

    def session_root(session_id: str) -> Path:
        return tmp_path / session_id

    def text_from_payload(payload, original_args, public_tool_name) -> str:
        return str(payload.get("request") or original_args.get("request") or "")

    def parse_bool(value, default: bool) -> bool:
        if value is None:
            return default
        return str(value).lower() not in {"0", "false", "no"}

    def start_agent_job(payload, public_tool_name, original_args, task):
        calls["start"].append((payload, public_tool_name, original_args, task))
        return {"ok": True, "mode": "start", "task": task}

    def compact_agent_status(job_id, include_events=False):
        calls["status"].append((job_id, include_events))
        return {"ok": True, "mode": "status", "job_id": job_id}

    def compact_agent_terminal_response(job_id):
        calls["result"].append(job_id)
        return {"ok": True, "mode": "result", "job_id": job_id}

    def load_state(job_id: str) -> dict[str, Any]:
        return dict(states.get(job_id) or {})

    def write_state(state: dict[str, Any]) -> None:
        stored = dict(state)
        states[str(stored["job_id"])] = stored
        calls["writes"].append(stored)

    def append_event(job_id, event_type, message, payload=None, *, step=None):
        calls["events"].append(
            {
                "job_id": job_id,
                "event_type": event_type,
                "message": message,
                "payload": payload or {},
                "step": step,
            }
        )

    router = AgentJobActionRouter(
        public_tool=public_tool,
        public_args=public_args,
        make_session_id=make_session_id,
        session_root=session_root,
        text_from_payload=text_from_payload,
        parse_bool=parse_bool,
        start_agent_job=start_agent_job,
        compact_agent_status=compact_agent_status,
        compact_agent_terminal_response=compact_agent_terminal_response,
        load_state=load_state,
        write_state=write_state,
        append_event=append_event,
        selector_runner=selector,
    )
    return router, calls, states, selector


def test_job_action_router_start_does_not_run_selector(tmp_path: Path) -> None:
    router, calls, _states, selector = _router_fixture(tmp_path)

    result = router.handle({"tool": "vulkan_helper", "request": "analyze"})

    assert result == {"ok": True, "mode": "start", "task": "analyze"}
    assert calls["start"]
    assert selector.calls == []


def test_job_action_router_status_and_result(tmp_path: Path) -> None:
    router, calls, _states, selector = _router_fixture(tmp_path)

    status = router.handle({"action": "status", "job_id": "job-1"})
    result = router.handle({"action": "result", "job_id": "job-1"})

    assert status == {"ok": True, "mode": "status", "job_id": "job-1"}
    assert result == {"ok": True, "mode": "result", "job_id": "job-1"}
    assert calls["status"] == [("job-1", True)]
    assert calls["result"] == ["job-1"]
    assert selector.calls == []


def test_job_action_router_cancel_sets_cancel_requested(tmp_path: Path) -> None:
    router, calls, states, selector = _router_fixture(tmp_path)

    result = router.handle({"action": "cancel", "job_id": "job-1"})

    assert result == {"ok": True, "mode": "status", "job_id": "job-1"}
    assert states["job-1"]["status"] == "cancel_requested"
    assert calls["writes"] == [{"job_id": "job-1", "status": "cancel_requested"}]
    assert calls["events"][0]["event_type"] == "cancel_requested"
    assert selector.calls == []


def test_job_action_router_cancel_missing_state_returns_status(tmp_path: Path) -> None:
    router, calls, _states, selector = _router_fixture(tmp_path)

    result = router.handle({"action": "cancel", "job_id": "missing"})

    assert result == {"ok": True, "mode": "status", "job_id": "missing"}
    assert calls["writes"] == []
    assert calls["events"] == []
    assert selector.calls == []


def test_job_action_router_selector_path_for_non_job_public_tool(tmp_path: Path) -> None:
    router, calls, _states, selector = _router_fixture(tmp_path)

    result = router.handle(
        {
            "tool": "repo_public",
            "action": "direct_tool",
            "request": "inspect",
            "allow_command": "false",
            "timeout_seconds": 999,
            "arguments": {"user_consent": "ok"},
        }
    )

    assert result == {"ok": True, "mode": "selector", "task": "inspect"}
    assert calls["start"] == []
    assert selector.calls[0]["public_tool_name"] == "repo_public"
    assert selector.calls[0]["allow_command"] is False
    assert selector.calls[0]["user_consent"] == "ok"
    assert selector.calls[0]["timeout_seconds"] == 240
    assert selector.calls[0]["root"] == tmp_path / "session"
