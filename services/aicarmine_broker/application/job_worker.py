"""Background agent job worker application service."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import traceback
from typing import Any, Callable


LoadState = Callable[[str], dict[str, Any]]
WriteState = Callable[[dict[str, Any]], None]
AppendEvent = Callable[..., None]
JobRoot = Callable[[str], Path]
WriteJson = Callable[[Path, Any], str]
PlannerRunner = Callable[[str], Any]
AgentRunner = Callable[[dict[str, Any]], dict[str, Any]]
SummaryBuilder = Callable[[dict[str, Any]], str]


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
        except Exception as exc:
            self._write_failure(job_id, state, exc)

    def _run_legacy_oneshot(self, job_id: str, state: dict[str, Any]) -> None:
        run_payload = dict(state.get("request_payload") or {})
        run_args = dict(run_payload.get("arguments") or {})
        for key in ("action", "job_action", "job_id"):
            run_payload.pop(key, None)
            run_args.pop(key, None)
        run_payload["arguments"] = run_args
        run_payload["mode"] = "tool_helper"
        run_payload["session_id"] = job_id
        self.append_event(
            job_id,
            "agent_call",
            "Running legacy one-shot broker pipeline in background.",
            {"payload_keys": sorted(run_payload.keys())},
            step=1,
        )
        result = self.agent_runner(run_payload)
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
        state["error"] = error_text[-12000:]
        state["final_path"] = str(root / "error.txt")
        state["final_summary"] = f"Agent job failed: {type(exc).__name__}: {exc}"
        self.write_state(state)
        self.append_event(
            job_id,
            "job_failed",
            state["final_summary"],
            {"error_type": type(exc).__name__},
            step=999,
        )
