"""Pure builders for compact terminal job responses."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .response_values import compact_text, event_digest
from ..public_payload.history_ledger import build_public_result_digest


def build_missing_job_response(job_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "service": "vulkan_agent",
        "tool_name": "vulkan_helper",
        "error": "job_not_found",
        "job_id": job_id,
    }


def verify_local_final_path(path: str | Path, *, expected_type: str = "json") -> dict[str, Any]:
    raw_path = str(path or "")
    result: dict[str, Any] = {
        "final_path": raw_path,
        "final_path_verified": False,
        "final_path_exists": False,
        "final_path_readable": False,
        "final_path_audience": "operator_local_filesystem",
        "openwebui_can_read_final_path": False,
    }
    if not raw_path:
        result["final_path_error"] = "missing_path"
        return result
    try:
        final_path = Path(raw_path)
        result["final_path_absolute"] = final_path.is_absolute()
        if not final_path.is_absolute():
            result["final_path_error"] = "not_absolute"
            return result
        result["final_path_exists"] = final_path.exists()
        if not final_path.exists():
            result["final_path_error"] = "missing_file"
            return result
        if not final_path.is_file():
            result["final_path_error"] = "not_a_file"
            return result
        raw = final_path.read_bytes()
        result["final_path_readable"] = True
        result["final_path_size_bytes"] = len(raw)
        result["final_path_sha256"] = hashlib.sha256(raw).hexdigest()
        result["final_path_mtime"] = final_path.stat().st_mtime
        if not raw:
            result["final_path_error"] = "empty_file"
            return result
        text = raw.decode("utf-8", errors="replace")
        if expected_type == "json":
            result["final_path_content_type"] = "application/json"
            loaded = json.loads(text)
            if loaded in ({}, []):
                result["final_path_error"] = "empty_json"
                return result
        else:
            result["final_path_content_type"] = "text/plain"
            if not text.strip():
                result["final_path_error"] = "empty_text"
                return result
        result["final_path_verified"] = True
        return result
    except json.JSONDecodeError:
        result["final_path_error"] = "invalid_json"
        return result
    except Exception as exc:
        result["final_path_error"] = "read_failed"
        result["final_path_error_type"] = type(exc).__name__
        result["final_path_error_detail"] = str(exc)[:1000]
        return result


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
    audience: str = "operator",
) -> dict[str, Any]:
    status = str(state.get("status") or "unknown")
    public_tool = str(state.get("public_tool_name") or "vulkan_helper")
    final_path = str(state.get("final_path") or "")
    final_markdown_path = str(state.get("final_markdown_path") or "")
    final_path_verification = verify_local_final_path(final_path, expected_type="json")
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
    local_paths = {
        "local_final_path": final_path,
        "local_final_markdown_path": final_markdown_path,
        "local_events_path": events_path,
        "local_workspace": state.get("workspace"),
        "final_path_verification": final_path_verification,
        "note": (
            "Local paths are for the local operator only. OpenWebUI must use "
            "inline payload fields."
        ),
    }
    full_result_hint = (
        "Full result is available in final_path and was verified readable by the local runtime."
        if final_path_verification.get("final_path_verified") is True
        else "final_path was expected but is not currently verified readable."
    )
    if audience == "openwebui":
        full_result_hint = (
            "Full result is available in final_path for the local operator only when "
            "verified; OpenWebUI cannot read local paths, so inline evidence is provided "
            "in tool_context_for_30b."
        )
    openwebui_usage = {
        "primary_answer_field": "answer_for_30b",
        "structured_context_field": "tool_context_for_30b",
        "rule": (
            "Answer the user from answer_for_30b; use structured context only "
            "for evidence-bound details."
        ),
    }
    if audience == "openwebui":
        openwebui_usage = {
            "primary_payload_fields": [
                "payload_index_for_30b",
                "priority_evidence_for_30b",
                "tool_context_for_30b",
                "openwebui_usage",
            ],
            "structured_context_field": "tool_context_for_30b",
            "rule": (
                "OpenWebUI cannot read local filesystem paths. Use inline "
                "payload_index_for_30b, priority_evidence_for_30b and "
                "tool_context_for_30b when present; local paths are only "
                "operator diagnostics."
            ),
        }

    public_final_path_verification = dict(final_path_verification)
    if audience == "openwebui":
        public_final_path_verification.pop("final_path", None)

    response = {
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
        "full_result_available": bool(final_path_verification.get("final_path_verified")),
        "full_result_hint": full_result_hint,
        "final_path_verification": public_final_path_verification,
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
        "openwebui_usage": openwebui_usage,
        "result": result_digest,
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": context_alias,
        "structured_context_for_30b": context_alias,
        "structured_result_for_30b": context_alias,
        "artifacts": [] if audience == "openwebui" else artifacts,
        "events_tail_digest": events,
    }
    if audience == "openwebui":
        response["operator_diagnostics"] = local_paths
    else:
        response["final_path"] = final_path
        response["final_markdown_path"] = final_markdown_path
        response["events_path"] = events_path
    return response
