"""Agent job lifecycle application service."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, MutableMapping


InitJobDb = Callable[[], None]
MakeSessionId = Callable[[str], str]
JobRoot = Callable[[str], Path]
WriteState = Callable[[dict[str, Any]], None]
AppendEvent = Callable[..., None]
JobUrl = Callable[[str], str]
WaitForTerminal = Callable[[str, int], dict[str, Any]]
Worker = Callable[[str], None]


@dataclass(frozen=True)
class AgentJobLifecycle:
    """Create queued 3572 jobs and launch the background worker."""

    init_agent_job_db: InitJobDb
    make_session_id: MakeSessionId
    agent_job_root: JobRoot
    write_state: WriteState
    append_event: AppendEvent
    job_url: JobUrl
    wait_for_terminal: WaitForTerminal
    worker: Worker
    background_threads: MutableMapping[str, Any]
    lock: Any
    agent_default_max_steps: int
    approval_mode: str
    return_wait_seconds: int
    agentic_planner_enabled: bool
    planner_url: str
    planner_model: str
    selector_url: str
    selector_model: str
    thread_factory: Callable[..., Any] = threading.Thread
    now: Callable[[], float] = time.time
    uuid_token: Callable[[], str] = lambda: uuid.uuid4().hex[:8]

    def start(
        self,
        payload: dict[str, Any],
        public_tool_name: str,
        original_args: dict[str, Any],
        task: str,
    ) -> dict[str, Any]:
        self.init_agent_job_db()
        requested_job_id = str(
            original_args.get("job_id") or payload.get("job_id") or ""
        ).strip()
        job_id = (
            self.make_session_id(requested_job_id)
            if requested_job_id
            else self.make_session_id("job-" + self.uuid_token())
        )
        root = self.agent_job_root(job_id)
        return_mode = str(
            original_args.get("return_mode") or payload.get("return_mode") or "wait"
        ).strip().lower()
        state = {
            "job_id": job_id,
            "status": "queued",
            "goal": task,
            "public_tool_name": public_tool_name,
            "created_at": self.now(),
            "updated_at": self.now(),
            "workspace": str(root),
            "request_payload": payload,
            "original_args": original_args,
            "max_steps": int(
                original_args.get("max_steps")
                or payload.get("max_steps")
                or self.agent_default_max_steps
            ),
            "approval_mode": str(
                original_args.get("approval_mode")
                or payload.get("approval_mode")
                or self.approval_mode
            ),
            "return_mode": return_mode,
            "agentic_planner_enabled": self.agentic_planner_enabled,
            "planner_url": self.planner_url,
            "planner_model": self.planner_model,
            "selector_url": self.selector_url,
            "selector_model": self.selector_model,
        }
        self.write_state(state)
        self.append_event(
            job_id,
            "job_queued",
            "Agent job queued.",
            {"goal": task},
            step=0,
        )
        self._ensure_worker_thread(job_id)
        started = self._started_response(
            public_tool_name=public_tool_name,
            job_id=job_id,
            root=root,
        )
        wait_seconds = int(
            original_args.get("wait_seconds")
            or payload.get("wait_seconds")
            or self.return_wait_seconds
        )
        if return_mode in {"background", "async", "fire_and_forget"}:
            return started
        waited = self.wait_for_terminal(job_id, wait_seconds)
        waited["started_job"] = started
        waited["job_id"] = job_id
        waited["job_url"] = self.job_url(job_id)
        waited["workspace"] = str(root)
        waited["tool_name"] = public_tool_name
        waited["tool_result_for"] = public_tool_name
        waited["operation_id"] = public_tool_name
        waited["called_by_30b"] = public_tool_name
        return waited

    def _ensure_worker_thread(self, job_id: str) -> None:
        with self.lock:
            existing = self.background_threads.get(job_id)
            if not existing or not existing.is_alive():
                thread = self.thread_factory(
                    target=self.worker,
                    args=(job_id,),
                    daemon=True,
                    name=f"aicarmine-agent-job-{job_id}",
                )
                self.background_threads[job_id] = thread
                thread.start()

    def _started_response(
        self,
        *,
        public_tool_name: str,
        job_id: str,
        root: Path,
    ) -> dict[str, Any]:
        dashboard_url = self.job_url(job_id)
        return {
            "ok": True,
            "service": "vulkan_agent",
            "mode": "agent_job_started",
            "verdict": "AGENT_JOB_STARTED",
            "tool_name": public_tool_name,
            "tool_result_for": public_tool_name,
            "operation_id": public_tool_name,
            "called_by_30b": public_tool_name,
            "job_id": job_id,
            "status": "queued",
            "workspace": str(root),
            "job_url": dashboard_url,
            "message_for_30b": (
                f"Agent job started internally: {job_id}. The tool call will wait "
                "for a terminal state before returning to OpenWebUI."
            ),
            "summary_for_30b": (
                f"Agent job started internally: {job_id}. Waiting for terminal state."
            ),
            "content": f"Agent job started internally: {job_id}\nDashboard: {dashboard_url}",
        }
