"""Pure builders for compact terminal job responses."""
from __future__ import annotations

from typing import Any

from .job_response_values import compact_text, event_digest
from .public_history_ledger import build_public_result_digest


def build_missing_job_response(job_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "service": "vulkan_agent",
        "tool_name": "vulkan_helper",
        "error": "job_not_found",
        "job_id": job_id,
    }


def build_compact_terminal_response(
    *,
    job_id: str,
    state: dict[str, Any],
    final_data: dict[str, Any],
    events_tail: list[dict[str, Any]],
    events_path: str,
    job_url_value: str,
    public_result_inline_chars: int,
    public_summary_chars: int,
    public_answer_chars: int,
) -> dict[str, Any]:
    status = str(state.get("status") or "unknown")
    public_tool = str(state.get("public_tool_name") or "vulkan_helper")
    final_path = str(state.get("final_path") or "")
    final_markdown_path = str(state.get("final_markdown_path") or "")
    summary = compact_text(
        state.get("final_summary") or state.get("error") or "",
        public_summary_chars,
    )
    events = [event_digest(ev) for ev in events_tail[-5:]]
    artifacts = [p for p in (final_path, final_markdown_path, events_path) if p]
    result_digest = build_public_result_digest(
        state.get("result") or {},
        public_result_inline_chars,
    )
    tool_context = state.get("tool_context_for_30b")
    if not isinstance(tool_context, dict):
        for key in (
            "tool_context_for_30b",
            "agent_context_for_30b",
            "structured_context_for_30b",
            "structured_result_for_30b",
        ):
            if isinstance(final_data.get(key), dict):
                tool_context = final_data.get(key)
                break
    answer = (
        state.get("answer_for_30b")
        or final_data.get("answer_for_30b")
        or (tool_context.get("answer_for_30b") if isinstance(tool_context, dict) else "")
        or summary
    )
    answer = compact_text(answer, public_answer_chars)
    next_action = (
        state.get("next_action_for_30b")
        or final_data.get("next_action_for_30b")
        or (tool_context.get("next_action_for_30b") if isinstance(tool_context, dict) else {})
    )
    if not isinstance(next_action, dict):
        next_action = {}
    if not isinstance(tool_context, dict):
        tool_context = {
            "type": "agentic_loop_complete_structured_context_unavailable",
            "contract_type": "structured_agentic_loop_context_unavailable",
            "job": {"job_id": job_id, "status": status, "goal": state.get("goal")},
            "answer_for_30b": answer,
            "next_action_for_30b": next_action,
            "result": result_digest,
            "events_tail_digest": [event_digest(ev) for ev in events_tail[-20:]],
        }

    context_alias = {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }
    return {
        "ok": True,
        "job_ok": status == "completed",
        "service": "vulkan_agent",
        "mode": "agent_job_final_compact",
        "tool_name": public_tool,
        "tool_result_for": public_tool,
        "called_by_30b": public_tool,
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "job_url": job_url_value,
        "final_path": final_path,
        "final_markdown_path": final_markdown_path,
        "events_path": events_path,
        "full_result_available": bool(final_path),
        "full_result_hint": (
            "Open final_path/final_markdown_path or the job_url for the complete "
            "untruncated result."
        ),
        "answer_for_30b": answer,
        "summary_for_30b": summary,
        "message_for_30b": answer,
        "evidence_digest_for_30b": (
            tool_context.get("evidence_digest_for_30b")
            if isinstance(tool_context, dict)
            else ""
        ),
        "final_summary": summary,
        "next_action_for_30b": next_action,
        "working_memory_for_30b": state.get("working_memory_for_30b")
        or final_data.get("working_memory_for_30b")
        or {},
        "evidence_contract": state.get("evidence_contract")
        or final_data.get("evidence_contract")
        or {},
        "planner_emission_interpreter": state.get("planner_emission_interpreter")
        or final_data.get("planner_emission_interpreter")
        or {},
        "openwebui_usage": {
            "primary_answer_field": "answer_for_30b",
            "structured_context_field": "tool_context_for_30b",
            "rule": (
                "Answer the user from answer_for_30b; use structured context only "
                "for evidence-bound details."
            ),
        },
        "result": result_digest,
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": context_alias,
        "structured_context_for_30b": context_alias,
        "structured_result_for_30b": context_alias,
        "artifacts": artifacts,
        "events_tail_digest": events,
    }
