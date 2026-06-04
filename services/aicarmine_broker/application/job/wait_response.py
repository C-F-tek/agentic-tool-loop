"""Pure builder for job wait-timeout responses."""
from __future__ import annotations

from typing import Any

from .response_values import event_digest


def build_wait_timeout_response(
    *,
    job_id: str,
    last_status: dict[str, Any],
    timeout_seconds: int,
    events_tail: list[dict[str, Any]],
) -> dict[str, Any]:
    response = dict(last_status)
    response["mode"] = "agent_job_wait_timeout"
    response["wait_completed"] = False
    response["wait_timeout_seconds"] = timeout_seconds
    response["events_tail_digest"] = [event_digest(ev) for ev in events_tail]
    memory = (
        response.get("working_memory_for_30b")
        if isinstance(response.get("working_memory_for_30b"), dict)
        else {}
    )
    candidates = (
        memory.get("candidate_next_actions")
        if isinstance(memory.get("candidate_next_actions"), list)
        else []
    )
    rejections = (
        memory.get("rejections_tail")
        if isinstance(memory.get("rejections_tail"), list)
        else []
    )
    response["message_for_30b"] = (
        f"Agent job {job_id} is still running after {timeout_seconds}s; "
        f"status={response.get('status')} step={response.get('current_step')} "
        f"message={response.get('status_message') or ''}. "
        f"candidate_next_actions={len(candidates)} recent_rejections={len(rejections)}. "
        "The structured working_memory_for_30b/evidence_contract fields are included "
        "in this same result; use them before deciding whether to call "
        "action='status' or action='result'."
    )
    response["answer_for_30b"] = response["message_for_30b"]
    response["next_action_for_30b"] = {
        "action": "continue_same_openwebui_context",
        "status": response.get("status"),
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
    response["continuation_surface"] = {
        "public_tool": "vulkan_helper",
        "current_call_wait_timed_out": True,
        "same_job_id": job_id,
        "call_protocol": {"action": "status", "job_id": job_id},
        "result_protocol": {"action": "result", "job_id": job_id},
    }
    return response
