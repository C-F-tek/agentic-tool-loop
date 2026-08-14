"""Terminal answer and next-action helpers for the outer OpenWebUI model."""

from __future__ import annotations

import json
from typing import Any, Callable


ResultTextBuilder = Callable[[dict[str, Any]], str]


def _has_successful_inline_evidence(result: dict[str, Any]) -> bool:
    if result.get("partial_products_for_30b") not in (None, "", [], {}):
        return True
    if result.get("best_partial_product_for_30b") not in (None, "", [], {}):
        return True
    history = result.get("history") if isinstance(result.get("history"), list) else []
    for item in history:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = str(tool_result.get("tool") or "")
        if tool and tool != "controller_guard" and tool_result.get("ok") is True:
            return True
    return False


def _coverage_missing(result: dict[str, Any]) -> tuple[bool, list[str]]:
    status = _coverage_status(result)
    return bool(status.get("coverage_gap")), list(status.get("missing_owner_paths") or [])


def _coverage_status(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "coverage_gap": False,
            "missing_owner_paths": [],
            "coverage_contract_invalid": True,
            "coverage_contract_error": "result_not_object",
            "received_type": type(result).__name__,
        }
    contract = result.get("evidence_contract") if isinstance(result.get("evidence_contract"), dict) else {}
    contract_invalid = False
    invalid_reason = ""
    if result.get("evidence_contract") not in (None, "", [], {}) and not isinstance(result.get("evidence_contract"), dict):
        contract_invalid = True
        invalid_reason = "evidence_contract_not_object"
    coverage = (
        contract.get("minimum_read_coverage")
        if isinstance(contract.get("minimum_read_coverage"), dict)
        else {}
    )
    if contract.get("minimum_read_coverage") not in (None, "", [], {}) and not isinstance(contract.get("minimum_read_coverage"), dict):
        contract_invalid = True
        invalid_reason = invalid_reason or "minimum_read_coverage_not_object"
    if coverage:
        coverage_satisfied = coverage.get("coverage_satisfied")
        raw_missing = coverage.get("missing_owner_paths")
    else:
        coverage_satisfied = result.get("coverage_satisfied")
        if coverage_satisfied is None:
            coverage_satisfied = contract.get("coverage_satisfied")
        raw_missing = result.get("missing_owner_paths")
        if raw_missing in (None, "", [], {}):
            raw_missing = contract.get("missing_owner_paths")
    if isinstance(raw_missing, dict) and isinstance(raw_missing.get("items"), list):
        raw_missing = raw_missing.get("items")
    missing = [str(path) for path in raw_missing] if isinstance(raw_missing, list) else []
    return {
        "coverage_gap": coverage_satisfied is False,
        "coverage_satisfied": coverage_satisfied,
        "missing_owner_paths": missing,
        "coverage_contract_invalid": contract_invalid,
        "coverage_contract_error": invalid_reason,
    }


def _terminal_evidence_first_text(
    status_text: str,
    summary: str,
    result: dict[str, Any],
    
    execution_evidence_digest_text: ResultTextBuilder,
) -> str:
    evidence = execution_evidence_digest_text(result)
    if not evidence:
        return ""
    blocked_by = str(result.get("blocked_by") or "none")
    return (
        "Il loop agentico interno non ha prodotto un final validato dal controller, "
        "ma ha restituito evidenza concreta inline. Rispondi dalla evidenza qui sotto "
        "con limiti espliciti; non trattare lo stato terminale come assenza di contenuto.\n\n"
        + evidence
        + f"\n\nStato terminale: status={status_text}; blocker={blocked_by}.\n\n"
        + "Sintesi terminale:\n"
        + summary
    )


def answer_for_openwebui(
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
    
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
            return code_product_answer
        return summary
    if status_text == "blocked_needs_attention":
        blocked_by = str(result.get("blocked_by") or "unknown")
        extra: list[str] = []
        coverage_status = _coverage_status(result)
        coverage_gap = bool(coverage_status.get("coverage_gap"))
        missing_paths = list(coverage_status.get("missing_owner_paths") or [])
        if coverage_gap:
            extra.append(
                "Coverage non soddisfatta: coverage_satisfied=false; "
                f"missing_owner_paths={missing_paths[:20]}"
            )
        elif coverage_status.get("coverage_contract_invalid"):
            extra.append(
                "Coverage contract non interpretabile: "
                + str(coverage_status.get("coverage_contract_error") or "unknown")
            )
        partial_answer = partial_product_answer_text(result)
        if partial_answer:
            extra.append(partial_answer)
        evidence_first = _terminal_evidence_first_text(
            status_text,
            summary,
            result,
            execution_evidence_digest_text=execution_evidence_digest_text,
        )
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
        if evidence_first:
            return evidence_first + suffix
        return (
            "Il loop agentico interno si è fermato prima del final del planner. "
            f"Stato={status_text}; blocker={blocked_by}.\n\n{summary}{suffix}"
        )
    if status_text == "max_steps_reached":
        partial_answer = partial_product_answer_text(result)
        evidence_first = _terminal_evidence_first_text(
            status_text,
            summary,
            result,
            execution_evidence_digest_text=execution_evidence_digest_text,
        )
        if evidence_first:
            return (partial_answer + "\n\n" if partial_answer else "") + evidence_first
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
    coverage_gap, missing_paths = _coverage_missing(result)
    coverage_status = _coverage_status(result)
    if coverage_gap:
        action = "report_coverage_required_with_missing_owner_paths"
    if status_text == "blocked_needs_attention":
        if coverage_gap:
            action = "report_coverage_required_with_missing_owner_paths"
        elif _has_successful_inline_evidence(result):
            action = "answer_user_from_inline_evidence_with_explicit_limits"
        else:
            action = "report_blocker_and_use_structured_context_for_diagnosis"
    elif status_text == "completed":
        action = "answer_user_with_final_result"
    elif status_text == "max_steps_reached":
        if _has_successful_inline_evidence(result):
            action = "answer_user_from_inline_evidence_with_explicit_limits"
        else:
            action = "report_incomplete_loop_and_relevant_last_evidence"
    return {
        "action": action,
        "status": status_text,
        "blocked_by": result.get("blocked_by"),
        "coverage_satisfied": False if coverage_gap else None,
        "missing_owner_paths": missing_paths if coverage_gap else None,
        "coverage_contract_invalid": (
            True if coverage_status.get("coverage_contract_invalid") else None
        ),
        "coverage_contract_error": coverage_status.get("coverage_contract_error") or None,
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
