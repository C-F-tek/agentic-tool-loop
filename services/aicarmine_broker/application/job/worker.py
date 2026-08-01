"""Background agent job worker applifrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

cation service."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import time
import traceback
from typing import Any, Callable

from ..public_payload.terminal_sanitizer import public_terminal_sanitize_text


LoadState = Callable[[str], dict[str, Any]]
WriteState = Callable[[dict[str, Any]], None]
AppendEvent = Callable[..., None]
JobRoot = Callable[[str], Path]
WriteJson = Callable[[Path, Any], str]
PlannerRunner = Callable[[str], Any]
AgentRunner = Callable[[dict[str, Any]], dict[str, Any]]
SummaryBuilder = Callable[[dict[str, Any]], str]
TerminalFinalizer = Callable[
    [str, dict[str, Any], str, str, dict[str, Any] | None],
    dict[str, Any],
]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentJobWorker:
    """Run one background 3572 job without owning persistence primitives."""

    load_state: LoadState
    write_state: WriteState
    append_event: AppendEvent
    agent_job_root: JobRoot
    write_json: WriteJson
    planner_runner: PlannerRunner
    agent_runner: AgentRunner
    summary_from_result: SummaryBuilder
    agentic_planner_enabled: bool
    agentic_fallback_oneshot: bool
    terminal_finalizer: TerminalFinalizer | None = None
    legacy_oneshot_timeout_seconds: int = 120

    def run(self, job_id: str) -> None:
        state = self.load_state(job_id)
        if not state:
            return
        state["status"] = "running"
        self.write_state(state)
        self.append_event(
            job_id,
            "job_started",
            "Background agent job started.",
            {"job_id": job_id},
            step=0,
        )
        try:
            if self.agentic_planner_enabled:
                self.planner_runner(job_id)
                return
            if not self.agentic_fallback_oneshot:
                raise RuntimeError(
                    "Agentic planner is disabled and AICARMINE_AGENTIC_FALLBACK_ONESHOT=0; "
                    "refusing legacy one-shot fallback for OpenWebUI wrapper job."
                )
            self._run_legacy_oneshot(job_id, state)
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            self._write_failure(job_id, state, exc)

    def _run_legacy_oneshot(self, job_id: str, state: dict[str, Any]) -> None:
        run_payload = dict(state.get("request_payload") or {})
        run_args = dict(run_payload.get("arguments") or {})
        timeout_seconds, timeout_meta = self._legacy_oneshot_timeout_seconds(state)
        for key in ("action", "job_action", "job_id"):
            run_payload.pop(key, None)
            run_args.pop(key, None)
        if run_args.get("timeout_seconds") in (None, ""):
            run_args["timeout_seconds"] = timeout_seconds
        if run_payload.get("timeout_seconds") in (None, ""):
            run_payload["timeout_seconds"] = timeout_seconds
        run_payload["arguments"] = run_args
        run_payload["mode"] = "tool_helper"
        run_payload["session_id"] = job_id
        self.append_event(
            job_id,
            "agent_call",
            "Running legacy one-shot broker pipeline in background with bounded timeout metadata.",
            {
                "payload_keys": sorted(run_payload.keys()),
                "timeout_seconds": timeout_seconds,
                "timeout_contract": "propagated_to_legacy_payload_not_thread_alarm",
                **timeout_meta,
            },
            step=1,
        )
        started_at = time.perf_counter()
        result = self.agent_runner(run_payload)
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds > timeout_seconds:
            logger.warning(
                "Legacy one-shot returned after configured timeout metadata. "
                "job_id=%s elapsed_seconds=%.3f timeout_seconds=%s",
                job_id,
                elapsed_seconds,
                timeout_seconds,
            )
            self.append_event(
                job_id,
                "legacy_oneshot_timeout_metadata_exceeded",
                "Legacy one-shot returned after its configured timeout metadata.",
                {
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "timeout_seconds": timeout_seconds,
                    "hard_thread_kill_not_supported": True,
                },
                step=1,
            )
        root = self.agent_job_root(job_id)
        self.write_json(root / "final.json", result)
        final_summary = self.summary_from_result(
            result if isinstance(result, dict) else {"result": result}
        )
        (root / "final.md").write_text(final_summary, encoding="utf-8")
        state = self.load_state(job_id) or state
        state["status"] = "completed" if bool(result.get("ok")) else "failed"
        state["result_ok"] = bool(result.get("ok"))
        state["final_path"] = str(root / "final.json")
        state["final_markdown_path"] = str(root / "final.md")
        state["final_summary"] = final_summary[:12000]
        state["result"] = {
            "ok": bool(result.get("ok")),
            "verdict": result.get("verdict"),
            "internal_tool": (
                (result.get("internal_vulkan") or {}).get("tool_called_by_vulkan")
                if isinstance(result.get("internal_vulkan"), dict)
                else None
            ),
            "artifacts": result.get("artifacts"),
        }
        self.write_state(state)
        self.append_event(
            job_id,
            "job_finished",
            f"Job finished with status={state['status']}.",
            state.get("result", {}),
            step=2,
        )

    def _legacy_oneshot_timeout_seconds(self, state: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        request_payload = state.get("request_payload") if isinstance(state.get("request_payload"), dict) else {}
        original_args = state.get("original_args") if isinstance(state.get("original_args"), dict) else {}
        payload_args = request_payload.get("arguments") if isinstance(request_payload.get("arguments"), dict) else {}
        raw_timeout = None
        raw_source = "default"
        for source, container in (
            ("request_payload", request_payload),
            ("request_payload.arguments", payload_args),
            ("original_args", original_args),
        ):
            value = container.get("timeout_seconds") if isinstance(container, dict) else None
            if value not in (None, ""):
                raw_timeout = value
                raw_source = source
                break
        if raw_timeout in (None, ""):
            return int(max(15, min(int(self.legacy_oneshot_timeout_seconds or 120), 240))), {
                "timeout_source": raw_source,
                "timeout_defaulted": True,
            }
        try:
            parsed = int(float(str(raw_timeout).strip()))
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid legacy one-shot timeout; using default. source=%s type=%s preview=%r error_type=%s",
                raw_source,
                type(raw_timeout).__name__,
                str(raw_timeout)[:120],
                type(exc).__name__,
            )
            return int(max(15, min(int(self.legacy_oneshot_timeout_seconds or 120), 240))), {
                "timeout_source": raw_source,
                "timeout_defaulted": True,
                "timeout_parse_error_type": type(exc).__name__,
                "timeout_received_type": type(raw_timeout).__name__,
                "timeout_received_preview": str(raw_timeout)[:120],
            }
        bounded = int(max(15, min(parsed, 240)))
        return bounded, {
            "timeout_source": raw_source,
            "timeout_defaulted": False,
            "timeout_clamped": bounded != parsed,
        }

    def _write_failure(
        self,
        job_id: str,
        state: dict[str, Any],
        exc: Exception,
    ) -> None:
        root = self.agent_job_root(job_id)
        error_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        (root / "error.txt").write_text(error_text, encoding="utf-8")
        state = self.load_state(job_id) or state
        state["status"] = "failed"
        state["runtime_error_type"] = type(exc).__name__
        state["operator_error_path"] = str(root / "error.txt")
        public_error = public_terminal_sanitize_text(str(exc))[:1200]
        state["final_summary"] = (
            f"Agent job failed with {type(exc).__name__}. "
            "Inline evidence collected before the failure remains available in "
            "tool_context_for_30b."
        )
        if public_error:
            state["final_summary"] += f" Public error detail: {public_error}"
        history = state.get("history") if isinstance(state.get("history"), list) else []
        result = {
            "ok": False,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": public_error,
            "failure": {
                "error_type": type(exc).__name__,
                "public_error": public_error,
                "operator_error_written": True,
                "operator_diagnostics_required": True,
                "local_error_file_not_public_content": True,
            },
            "history": history,
        }
        if self.terminal_finalizer is not None:
            self.terminal_finalizer(
                job_id,
                state,
                "failed",
                state["final_summary"],
                result,
            )
            self.append_event(
                job_id,
                "job_failed",
                state["final_summary"],
                {
                    "error_type": type(exc).__name__,
                    "terminal_payload_written": True,
                    "tool_context_for_30b_required": True,
                },
                step=999,
            )
            return
        state["error"] = public_error
        state["final_path"] = str(root / "error.txt")
        self.write_state(state)
        self.append_event(
            job_id,
            "job_failed",
            state["final_summary"],
            {
                "error_type": type(exc).__name__,
                "terminal_payload_written": False,
                "tool_context_for_30b_required": True,
            },
            step=999,
        )
