"""Public agent payload action router."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .selector_runner import SelectorRunner


PublicTool = Callable[[dict[str, Any]], str]
PublicArgs = Callable[[dict[str, Any]], dict[str, Any]]
MakeSessionId = Callable[[str], str]
SessionRoot = Callable[[str], Path]
TextFromPayload = Callable[..., str]
ParseBool = Callable[[Any, bool], bool]
StartAgentJob = Callable[[dict[str, Any], str, dict[str, Any], str], dict[str, Any]]
CompactStatus = Callable[..., dict[str, Any]]
CompactTerminalResponse = Callable[..., dict[str, Any]]
LoadState = Callable[[str], dict[str, Any]]
WriteState = Callable[[dict[str, Any]], None]
AppendEvent = Callable[..., None]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentJobActionRouter:
    """Route a public broker payload to job lifecycle or selector dispatch.

    Handles the routing of public broker payloads to either the agent job
    lifecycle (start/status/result/cancel) or the selector runner for direct
    tool execution without background job creation.
    """

    public_tool: PublicTool
    public_args: PublicArgs
    make_session_id: MakeSessionId
    session_root: SessionRoot
    text_from_payload: TextFromPayload
    parse_bool: ParseBool
    start_agent_job: StartAgentJob
    compact_agent_status: CompactStatus
    compact_agent_terminal_response: CompactTerminalResponse
    load_state: LoadState
    write_state: WriteState
    append_event: AppendEvent
    selector_runner: SelectorRunner

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"payload": payload}
        public_tool_name = self.public_tool(payload)
        original_args = self.public_args(payload)
        session_id = self.make_session_id(
            str(payload.get("session_id") or original_args.get("session_id") or "")
        )
        root = self.session_root(session_id)
        task = self.text_from_payload(payload, original_args, public_tool_name)
        allow_command = self.parse_bool(
            payload.get("allow_command", original_args.get("allow_command", True)),
            True,
        )
        user_consent = str(
            payload.get("user_consent") or original_args.get("user_consent") or ""
        )
        timeout_seconds = self._timeout_seconds(payload, original_args)
        job_action, job_id = self._job_action(payload, original_args, public_tool_name)
        if job_action == "start":
            return self.start_agent_job(
                payload,
                public_tool_name,
                original_args,
                task,
            )
        if job_action == "status":
            return self.compact_agent_status(job_id, include_events=True)
        if job_action == "result":
            audience = self._result_audience(payload, original_args)
            return self.compact_agent_terminal_response(job_id, audience=audience)
        if job_action == "cancel":
            state = self.load_state(job_id)
            if not state:
                return self.compact_agent_status(job_id, include_events=True)
            state["status"] = "cancel_requested"
            self.write_state(state)
            self.append_event(
                job_id,
                "cancel_requested",
                "Cancel requested by user.",
                {},
                step=None,
            )
            return self.compact_agent_status(job_id, include_events=True)
        return self.selector_runner.run(
            public_tool_name=public_tool_name,
            task=task,
            original_args=original_args,
            root=root,
            allow_command=allow_command,
            user_consent=user_consent,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _timeout_seconds(
        payload: dict[str, Any],
        original_args: dict[str, Any],
    ) -> int:
        raw_timeout = None
        raw_source = "default"
        for source, container in (("payload", payload), ("arguments", original_args)):
            value = container.get("timeout_seconds") if isinstance(container, dict) else None
            if value not in (None, ""):
                raw_timeout = value
                raw_source = source
                break
        if raw_timeout in (None, ""):
            return 120
        try:
            timeout_seconds = float(str(raw_timeout).strip())
            if not math.isfinite(timeout_seconds):
                raise ValueError("timeout_seconds is not finite")
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid timeout_seconds from %s; using default timeout. "
                "received_type=%s received_preview=%r error_type=%s",
                raw_source,
                type(raw_timeout).__name__,
                str(raw_timeout)[:120],
                type(exc).__name__,
            )
            timeout_seconds = 120.0
        return int(max(15.0, min(timeout_seconds, 240.0)))

    @staticmethod
    def _job_action(
        payload: dict[str, Any],
        original_args: dict[str, Any],
        public_tool_name: str,
    ) -> tuple[str, str]:
        raw_job_action = str(
            original_args.get("job_action")
            or payload.get("job_action")
            or original_args.get("action")
            or payload.get("action")
            or ""
        ).strip().lower()
        job_id = str(original_args.get("job_id") or payload.get("job_id") or "").strip()
        start_actions = {"", "start", "job_start", "async", "background", "run", "execute"}
        status_actions = {"status", "job_status"}
        result_actions = {"result", "job_result", "final"}
        cancel_actions = {"cancel", "job_cancel"}
        if public_tool_name == "vulkan_helper" and (not job_id):
            return "start", job_id
        if raw_job_action in start_actions:
            return "start", job_id
        if raw_job_action in status_actions:
            return "status", job_id
        if raw_job_action in result_actions:
            return "result", job_id
        if raw_job_action in cancel_actions:
            return "cancel", job_id
        if public_tool_name == "vulkan_helper":
            return "start", job_id
        return raw_job_action, job_id

    @staticmethod
    def _result_audience(
        payload: dict[str, Any],
        original_args: dict[str, Any],
    ) -> str:
        raw = str(
            original_args.get("audience")
            or payload.get("audience")
            or ""
        ).strip().lower()
        if raw in {"operator", "openwebui", "internal"}:
            return raw
        return "operator"
