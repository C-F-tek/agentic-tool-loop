"""Pure builders for compact terminal job responses."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .response_values import compact_text, event_digest
from ..public_payload.history_ledger import build_public_result_digest
from ..public_payload.terminal_sanitizer import public_terminal_sanitize_text
from ..public_payload.terminal_result import public_terminal_result_for_30b
from ..public_payload.tool_context import public_tool_artifact_rows, successful_tool_turns


RepoReadContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
ArtifactPayloadLoader = Callable[[dict[str, Any]], dict[str, Any]]


def _inline_repo_read_item_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for key in ("content", "full_content", "content_view", "content_preview"):
        value = item.get(key) if isinstance(item, dict) else None
        if isinstance(value, str) and value:
            return value, {"source": f"state.{key}"}
    return "", {"source": "missing"}


def _identity_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    return result if isinstance(result, dict) else {}


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


def _build_evidence_guide_for_30b(
    *,
    goal: Any,
    status: str,
    answer: str,
    summary: str,
    tool_context: dict[str, Any],
    limit: int,
) -> str:
    artifacts = tool_context.get("artifacts") if isinstance(tool_context.get("artifacts"), list) else []
    history = tool_context.get("history") if isinstance(tool_context.get("history"), list) else []
    evidence_digest = str(tool_context.get("evidence_digest_for_30b") or "").strip()
    lines = [
        "GUIDA ALL'EVIDENZA INLINE PER IL 30B.",
        "Il testo sintetico non e' una risposta sostitutiva: usalo come indice per leggere il payload.",
        "Per rispondere in modo dettagliato usa prima payload_index_for_30b e priority_evidence_for_30b, poi tool_context_for_30b.",
        f"status={status}; artifacts={len(artifacts)}; history_rows={len(history)}",
        f"richiesta_utente={str(goal or '').strip()}",
    ]
    if answer:
        lines.extend(["", "Sommario/risposta del planner da usare come guida:", str(answer).strip()])
    elif summary:
        lines.extend(["", "Sommario terminale da usare come guida:", str(summary).strip()])
    if evidence_digest:
        lines.extend(["", "Evidenza eseguita inline:", evidence_digest])
    return public_terminal_sanitize_text(compact_text("\n".join(lines), limit))


def _strip_tool_context_narrative_duplicates(tool_context: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(tool_context)
    for key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "evidence_guide_for_30b",
        "final_answer",
        "composed_answer",
    ):
        cleaned.pop(key, None)
    usage = cleaned.get("openwebui_usage") if isinstance(cleaned.get("openwebui_usage"), dict) else {}
    if usage:
        usage = dict(usage)
        usage.pop("primary_answer_field", None)
        usage["top_level_evidence_guide_field"] = "evidence_guide_for_30b"
        usage["rule"] = (
            "tool_context_for_30b contains context/evidence only. The global "
            "evidence_guide_for_30b field is outside this JSON."
        )
        cleaned["openwebui_usage"] = usage
    return cleaned


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
    repo_read_item_full_content: RepoReadContentLoader | None = None,
    same_tool_artifact_payload: ArtifactPayloadLoader | None = None,
) -> dict[str, Any]:
    status = str(state.get("status") or "unknown")
    public_tool = str(state.get("public_tool_name") or "vulkan_helper")
    final_path = str(state.get("final_path") or "")
    final_markdown_path = str(state.get("final_markdown_path") or "")
    final_path_verification = verify_local_final_path(final_path, expected_type="json")
    summary = public_terminal_sanitize_text(
        compact_text(
            state.get("final_summary") or state.get("error") or "",
            public_summary_chars,
        )
    )
    events = [event_digest(ev) for ev in events_tail[-5:]]
    artifacts = [p for p in (final_path, final_markdown_path, events_path) if p]
    result_source = state.get("result") if isinstance(state.get("result"), dict) else {}
    result_source = dict(result_source)
    if "history" not in result_source and isinstance(state.get("history"), list):
        result_source["history"] = state.get("history")
    result_digest = build_public_result_digest(
        result_source,
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
    answer = public_terminal_sanitize_text(compact_text(answer, public_answer_chars))
    next_action = (
        state.get("next_action_for_30b")
        or final_data.get("next_action_for_30b")
        or (tool_context.get("next_action_for_30b") if isinstance(tool_context, dict) else {})
    )
    if not isinstance(next_action, dict):
        next_action = {}
    if not isinstance(tool_context, dict):
        content_loader = repo_read_item_full_content or _inline_repo_read_item_content
        artifact_loader = same_tool_artifact_payload or _identity_artifact_payload
        history = result_source.get("history") if isinstance(result_source.get("history"), list) else []
        public_result = public_terminal_result_for_30b(
            result_source,
            repo_read_item_full_content=content_loader,
        )
        public_artifacts = public_tool_artifact_rows(
            history,
            same_tool_artifact_payload=artifact_loader,
            repo_read_item_full_content=content_loader,
            code_product_build_state_kind="code_product_build_state",
        )
        public_successful_turns = successful_tool_turns(
            history,
            same_tool_artifact_payload=artifact_loader,
            repo_read_item_full_content=content_loader,
            code_product_build_state_kind="code_product_build_state",
        )
        if status == "failed" and public_artifacts:
            answer = public_terminal_sanitize_text(
                "Il job interno e' terminato con status=failed, ma l'evidenza "
                "raccolta prima del failure e' disponibile inline in "
                "tool_context_for_30b.artifacts e tool_context_for_30b.history. "
                "Non trattare il failure come assenza di contenuto; usa quei "
                f"campi per rispondere. Dettaglio failure: {summary}"
            )
        tool_context = {
            "type": "agentic_loop_complete_structured_context",
            "contract_type": "agentic_loop_complete_structured_context",
            "not_a_summary": True,
            "fallback_built_from_terminal_state": True,
            "job": {"job_id": job_id, "status": status, "goal": state.get("goal")},
            "top_level_evidence_guide_field": "evidence_guide_for_30b",
            "next_action_for_30b": next_action,
            "result": public_result or result_digest,
            "artifacts": public_artifacts,
            "successful_tool_turns": public_successful_turns,
            "history_count": public_result.get("history_count") if isinstance(public_result, dict) else None,
            "history_schema": public_result.get("history_schema") if isinstance(public_result, dict) else None,
            "history": public_result.get("history") if isinstance(public_result, dict) else [],
            "events_tail_digest": [event_digest(ev) for ev in events_tail[-20:]],
            "local_references_omitted_for_openwebui": True,
        }
    else:
        tool_context = _strip_tool_context_narrative_duplicates(tool_context)

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
        "evidence_guide_field": "evidence_guide_for_30b",
        "structured_context_field": "tool_context_for_30b",
        "rule": (
            "Use evidence_guide_for_30b as the reading guide for the inline "
            "payload. Do not answer from a short static sentence when "
            "tool_context_for_30b contains concrete evidence."
        ),
    }
    evidence_guide = _build_evidence_guide_for_30b(
        goal=state.get("goal"),
        status=status,
        answer=answer,
        summary=summary,
        tool_context=tool_context,
        limit=max(public_answer_chars, public_summary_chars),
    )
    if audience == "openwebui":
        openwebui_usage = {
            "primary_payload_fields": [
                "evidence_guide_for_30b",
                "payload_index_for_30b",
                "priority_evidence_for_30b",
                "tool_context_for_30b",
                "openwebui_usage",
            ],
            "evidence_guide_field": "evidence_guide_for_30b",
            "structured_context_field": "tool_context_for_30b",
            "rule": (
                "OpenWebUI cannot read local filesystem paths. Start from "
                "evidence_guide_for_30b, then use inline payload_index_for_30b, "
                "priority_evidence_for_30b and tool_context_for_30b. The guide "
                "is an evidence index, not a replacement for the concrete payload."
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
        "evidence_guide_for_30b": evidence_guide,
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
        for duplicate_key in ("answer_for_30b", "message_for_30b", "summary_for_30b", "content"):
            response.pop(duplicate_key, None)
    else:
        response["final_path"] = final_path
        response["final_markdown_path"] = final_markdown_path
        response["events_path"] = events_path
    return response
