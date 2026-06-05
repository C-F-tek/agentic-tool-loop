"""Terminal answer and next-action helpers for the outer OpenWebUI model."""

from __future__ import annotations

import json
from typing import Any, Callable


ResultTextBuilder = Callable[[dict[str, Any]], str]


def answer_for_openwebui(
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
    *,
    code_product_answer_text: ResultTextBuilder,
    execution_evidence_digest_text: ResultTextBuilder,
    partial_product_answer_text: ResultTextBuilder,
) -> str:
    """Top-level text the outer OpenWebUI model can use directly."""
    result = result if isinstance(result, dict) else {}
    summary = str(final_summary or "").strip() or "Job terminale senza final_summary."
    status_text = str(status or "unknown")
    if status_text == "completed":
        code_product_answer = code_product_answer_text(result)
        if code_product_answer:
            evidence = execution_evidence_digest_text(result)
            return code_product_answer if not evidence else code_product_answer + "\n\n" + evidence
        evidence = execution_evidence_digest_text(result)
        return summary if not evidence else summary + "\n\n" + evidence
    if status_text == "blocked_needs_attention":
        blocked_by = str(result.get("blocked_by") or "unknown")
        extra: list[str] = []
        partial_answer = partial_product_answer_text(result)
        if partial_answer:
            extra.append(partial_answer)
        raw_text = str(result.get("raw_planner_text") or "")
        if raw_text:
            extra.append("Raw planner output preview:\n" + raw_text[:3000])
        diagnostics = result.get("agent_flow_diagnostics") if isinstance(result.get("agent_flow_diagnostics"), dict) else {}
        raw_previews = diagnostics.get("last_non_empty_raw_previews") if isinstance(diagnostics, dict) else []
        if isinstance(raw_previews, list) and raw_previews:
            extra.append("Recent non-empty planner raw previews:\n" + "\n\n".join(str(x)[:900] for x in raw_previews[-3:]))
        if diagnostics.get("deterministic_strip_count"):
            extra.append(
                "Deterministic strip events occurred earlier in the same job: "
                + str(diagnostics.get("deterministic_strip_count"))
            )
        repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
        if repair:
            extra.append("Vulkan/GPU0 repair result:\n" + json.dumps(repair, ensure_ascii=False, default=str)[:3000])
        suffix = ("\n\n" + "\n\n".join(extra)) if extra else ""
        return (
            "Il loop agentico interno si è fermato prima del final del planner. "
            f"Stato={status_text}; blocker={blocked_by}.\n\n{summary}{suffix}"
        )
    if status_text == "max_steps_reached":
        partial_answer = partial_product_answer_text(result)
        if partial_answer:
            return (
                "Il loop agentico interno ha raggiunto il limite di step senza un final valido del planner.\n\n"
                + partial_answer
                + "\n\n"
                + summary
            )
        return (
            "Il loop agentico interno ha raggiunto il limite di step senza un final del planner.\n\n"
            + summary
        )
    partial_answer = partial_product_answer_text(result)
    if partial_answer:
        return (
            f"Risultato terminale del loop agentico: status={status_text}.\n\n"
            + partial_answer
            + "\n\n"
            + summary
        )
    return f"Risultato terminale del loop agentico: status={status_text}.\n\n{summary}"


def next_action_for_openwebui(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    status_text = str(status or "unknown")
    action = "answer_user_from_evidence_guide_for_30b"
    if status_text == "blocked_needs_attention":
        action = "report_blocker_and_use_structured_context_for_diagnosis"
    elif status_text == "completed":
        action = "answer_user_with_final_result"
    elif status_text == "max_steps_reached":
        action = "report_incomplete_loop_and_relevant_last_evidence"
    return {
        "action": action,
        "status": status_text,
        "blocked_by": result.get("blocked_by"),
        "do_not": [
            "do_not_ignore_evidence_guide_for_30b",
            "do_not_treat_job_url_as_the_only_result",
            "do_not_invent_repo_evidence_not_present_in_tool_context_for_30b",
        ],
        "use_fields_in_order": [
            "evidence_guide_for_30b",
            "tool_context_for_30b.best_partial_product_for_30b",
            "tool_context_for_30b.partial_products_for_30b",
            "tool_context_for_30b.artifacts",
            "tool_context_for_30b.evidence_contract_at_terminal",
            "tool_context_for_30b.history",
        ],
    }
