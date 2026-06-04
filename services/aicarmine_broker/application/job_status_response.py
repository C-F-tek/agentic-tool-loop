"""Pure builder for compact running job status responses."""
from __future__ import annotations

from typing import Any

from .job_response_values import event_digest


def build_compact_status_response(
    *,
    job_id: str,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    job_url_value: str,
) -> dict[str, Any]:
    memory = (
        state.get("working_memory_for_30b")
        if isinstance(state.get("working_memory_for_30b"), dict)
        else {}
    )
    evidence = (
        state.get("evidence_contract")
        if isinstance(state.get("evidence_contract"), dict)
        else {}
    )
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
        "Use working_memory_for_30b/evidence_contract from this same tool result "
        "before deciding the next call."
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
        "job_url": job_url_value,
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
        "structured_context_for_30b": state.get("structured_context_for_30b")
        or running_context,
        "structured_result_for_30b": state.get("structured_result_for_30b")
        or running_context,
        "message_for_30b": message_for_30b,
        "answer_for_30b": state.get("answer_for_30b") or message_for_30b,
    }
