"""Pure builder for job wait-timeout responses."""
from __future__ import annotations

from typing import Any

from .response_values import event_digest, strip_narrative_duplicates_from_context


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
    evidence_guide = (
        str(response.get("evidence_guide_for_30b") or "").strip()
        or (
        f"Agent job {job_id} is still running after {timeout_seconds}s; "
        f"status={response.get('status')} step={response.get('current_step')} "
        f"message={response.get('status_message') or ''}. "
        f"candidate_next_actions={len(candidates)} recent_rejections={len(rejections)}. "
        "The structured working_memory_for_30b/evidence_contract fields are included "
        "in this same result; use them before deciding whether to call "
        "action='status' or action='result'."
        )
    )
    for duplicate_key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
    ):
        response.pop(duplicate_key, None)
    response["evidence_guide_for_30b"] = evidence_guide
    for context_key in (
        "tool_context_for_30b",
        "agent_context_for_30b",
        "structured_context_for_30b",
        "structured_result_for_30b",
    ):
        if context_key in response:
            response[context_key] = strip_narrative_duplicates_from_context(response.get(context_key))
    response["openwebui_usage"] = {
        "evidence_guide_field": "evidence_guide_for_30b",
        "structured_context_field": "tool_context_for_30b",
        "rule": "Use evidence_guide_for_30b as the only global narrative guide; inspect working_memory_for_30b/evidence_contract before the next call.",
    }
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
