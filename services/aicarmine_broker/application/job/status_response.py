"""Pure builder for compact running job status responses."""
from __future__ import annotations

from typing import Any

from .response_values import event_digest, strip_narrative_duplicates_from_context
from ..shared.evidence_contract_summary import compact_evidence_contract_summary


def _running_evidence_guide(job_id: str, state: dict[str, Any], memory: dict[str, Any]) -> str:
    candidates = memory.get("candidate_next_actions") if isinstance(memory.get("candidate_next_actions"), list) else []
    rejections = memory.get("rejections_tail") if isinstance(memory.get("rejections_tail"), list) else []
    legacy_text = str(
        state.get("evidence_guide_for_30b")
        or state.get("answer_for_30b")
        or state.get("message_for_30b")
        or state.get("summary_for_30b")
        or ""
    ).strip()
    parts = [
        "GUIDA STATO LOOP INTERNO PER IL 30B.",
        f"Agent job {job_id} status={state.get('status')} step={state.get('current_step')} message={state.get('status_message') or ''}.",
        f"candidate_next_actions={len(candidates)} recent_rejections={len(rejections)}.",
        "Usa working_memory_for_30b, evidence_contract summary e tool_context_for_30b nello stesso payload; non usare path locali come contenuto.",
    ]
    if legacy_text:
        parts.extend(["", "Nota legacy convertita in guida unica:", legacy_text])
    return "\n".join(parts)


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
    evidence = compact_evidence_contract_summary(
        evidence,
        schema="planner_evidence_contract_status_summary.v1",
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
    evidence_guide = _running_evidence_guide(job_id, state, memory)
    tool_context = strip_narrative_duplicates_from_context(state.get("tool_context_for_30b") or running_context)
    agent_context = strip_narrative_duplicates_from_context(state.get("agent_context_for_30b") or running_context)
    structured_context = strip_narrative_duplicates_from_context(state.get("structured_context_for_30b") or running_context)
    structured_result = strip_narrative_duplicates_from_context(state.get("structured_result_for_30b") or running_context)

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
        "evidence_guide_for_30b": evidence_guide,
        "next_action_for_30b": state.get("next_action_for_30b", {}),
        "working_memory_for_30b": state.get("working_memory_for_30b", {}),
        "evidence_contract": evidence,
        "planner_emission_interpreter": state.get("planner_emission_interpreter", {}),
        "current_step": state.get("current_step"),
        "status_message": state.get("status_message", ""),
        "result": state.get("result", {}),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": agent_context,
        "structured_context_for_30b": structured_context,
        "structured_result_for_30b": structured_result,
    }
