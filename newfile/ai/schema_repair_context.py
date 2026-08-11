#!/usr/bin/env python3
"""Schema-repair context for provider rounds.

The local AI loop already has tool/broker evidence. This module turns that
runtime evidence into a compact provider-facing repair context so the next
GPU/NPU provider round is pushed toward valid patch-plan JSON instead of
summaries, context echo or schema-mismatched prose.

Pure/report-only module: no provider execution, no patch application, no
Blender runtime, no Git writes and no SQLite writes.
"""
from __future__ import annotations

from typing import Any

SCHEMA_REPAIR_CONTEXT_KIND = "schema_repair_provider_context"

SCHEMA_REPAIR_TRIGGER_REASONS = {
    "context_echo_detected",
    "json_parse_failure",
    "model_output_schema_mismatch",
    "valid_json_empty_recommendations",
    "recommendations_filtered_out",
    "evidence_ready_but_no_gpu_plan",
    "evidence_ready_but_no_tool_requests",
    "model_output_missing_required_fields",
    "repair_attempt_failed",
    "tool_requests_pending",
}

REQUIRED_TOP_LEVEL_KEYS = [
    "summary",
    "confidence",
    "recommendations",
    "tool_requests",
    "missing_evidence",
    "next_best_action",
]

RECOMMENDATION_TEMPLATE = {
    "id": "rec_short_snake_case_id",
    "area": "doc_code|doc_doc|code_code|workflow|validation|other",
    "status": "ready_for_patch_plan|needs_more_context|advisory_only",
    "target_files": ["relative/path.ext"],
    "rationale": "evidence-backed technical reason",
    "proposed_strategy": "small manual-review patch strategy",
    "risk": "low|medium|high",
    "validation_commands": ["command that does not apply patches or run Blender"],
    "stop_conditions": ["condition requiring human/manual review"],
}

TOOL_REQUEST_TEMPLATE = {
    "id": "need_specific_evidence",
    "tool": "allowlisted_runtime_tool_name",
    "reason": "specific missing evidence needed before deciding",
    "args": {},
}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.get("id"),
        "tool": result.get("tool"),
        "executed": result.get("executed"),
        "blocked": result.get("blocked"),
        "returncode": result.get("returncode"),
        "outputs": result.get("outputs", {}),
        "summary": result.get("summary", {}),
        "guardrails": result.get("guardrails", {}),
        "errors": result.get("errors", []),
    }


def collect_recent_runtime_tool_evidence(
    context_reports: list[dict[str, Any]],
    *,
    max_reports: int = 8,
    max_results_per_report: int = 6,
) -> list[dict[str, Any]]:
    """Return compact runtime-tool evidence from broker/feedback contexts."""

    evidence: list[dict[str, Any]] = []
    for item in reversed(context_reports):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in {"runtime_tool_feedback_context", "agent_runtime_tool_broker"}:
            continue
        tool_results = item.get("tool_results", [])
        if not isinstance(tool_results, list):
            tool_results = []
        summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
        evidence.append(
            {
                "kind": kind,
                "path": item.get("path"),
                "source": item.get("source") or summary.get("source"),
                "round": item.get("round") or summary.get("round"),
                "passed": item.get("passed"),
                "summary": {
                    "tool_request_count": summary.get("tool_request_count"),
                    "requested_tool_count": summary.get("requested_tool_count"),
                    "tool_execution_count": summary.get("tool_execution_count"),
                    "blocked_tool_count": summary.get("blocked_tool_count"),
                    "failed_tool_count": summary.get("failed_tool_count"),
                    "deterministic_fallback": summary.get("deterministic_fallback"),
                },
                "tool_results": [
                    _compact_tool_result(result)
                    for result in tool_results[:max_results_per_report]
                    if isinstance(result, dict)
                ],
            }
        )
        if len(evidence) >= max_reports:
            break
    return list(reversed(evidence))


def summarize_round_schema_failures(rounds: list[dict[str, Any]], *, max_rounds: int = 10) -> dict[str, Any]:
    """Summarize provider contract failures from previous rounds."""

    recent = rounds[-max_rounds:]
    reason_counts: dict[str, int] = {}
    schema_error_examples: list[str] = []
    for item in recent:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("empty_recommendations_reason") or "")
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        schema_errors = item.get("schema_errors", [])
        if isinstance(schema_errors, list):
            for error in schema_errors:
                text = str(error)
                if text and text not in schema_error_examples:
                    schema_error_examples.append(text)
                if len(schema_error_examples) >= 8:
                    break
    return {
        "round_count_seen": len(rounds),
        "recent_round_count": len(recent),
        "json_parse_error_count": sum(1 for item in recent if isinstance(item, dict) and not item.get("json_ok", True)),
        "schema_mismatch_count": sum(1 for item in recent if isinstance(item, dict) and item.get("model_output_schema_mismatch")),
        "context_echo_count": sum(1 for item in recent if isinstance(item, dict) and item.get("context_echo_detected")),
        "reason_counts": reason_counts,
        "schema_error_examples": schema_error_examples,
    }


def should_emit_schema_repair_context(
    *,
    rounds: list[dict[str, Any]],
    context_reports: list[dict[str, Any]],
    evidence_ready_for_manual_patch_count: int,
) -> bool:
    """Return true when provider needs stronger schema-repair steering."""

    if evidence_ready_for_manual_patch_count > 0:
        return True
    if collect_recent_runtime_tool_evidence(context_reports, max_reports=1):
        return True
    for item in rounds[-6:]:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("empty_recommendations_reason") or "")
        if reason in SCHEMA_REPAIR_TRIGGER_REASONS:
            return True
        if item.get("model_output_schema_mismatch") or item.get("context_echo_detected"):
            return True
    return False


def build_schema_repair_context_report(
    *,
    provider: str,
    rounds: list[dict[str, Any]],
    context_reports: list[dict[str, Any]],
    evidence_ready_for_manual_patch_count: int,
) -> dict[str, Any]:
    """Build a compact provider-facing schema-repair context report."""

    runtime_evidence = collect_recent_runtime_tool_evidence(context_reports)
    round_failures = summarize_round_schema_failures(rounds)
    has_runtime_evidence = bool(runtime_evidence)
    return {
        "kind": SCHEMA_REPAIR_CONTEXT_KIND,
        "provider": provider,
        "round_index_hint": len(rounds) + 1,
        "evidence_ready_for_manual_patch_count": evidence_ready_for_manual_patch_count,
        "runtime_tool_evidence_available": has_runtime_evidence,
        "runtime_tool_evidence_count": len(runtime_evidence),
        "round_schema_failures": round_failures,
        "runtime_tool_evidence": runtime_evidence,
        "directive": {
            "goal": "Convert available repository/tool evidence into schema-valid recommendations or explicit missing_evidence/tool_requests.",
            "must_not": [
                "Do not summarize the repository.",
                "Do not echo context files, execution plans or tool reports.",
                "Do not return Markdown or fenced code blocks when strict JSON is expected.",
                "Do not leave recommendations empty when evidence is ready unless missing_evidence explains the blocker.",
                "Do not request shell, git write, patch application, Blender runtime, provider execution or persistent memory writes.",
            ],
            "must_do": [
                "Return exactly one JSON object with all required top-level keys.",
                "Use runtime_tool_evidence as evidence, not as text to summarize.",
                "Prefer ready_for_patch_plan recommendations when target_files and validation_commands are known.",
                "When still uncertain, emit broker-compatible tool_requests instead of prose.",
                "Keep each recommendation small enough for manual review.",
            ],
            "required_top_level_keys": REQUIRED_TOP_LEVEL_KEYS,
            "recommendation_template": RECOMMENDATION_TEMPLATE,
            "tool_request_template": TOOL_REQUEST_TEMPLATE,
            "minimum_valid_response_when_ready": {
                "summary": "One sentence technical summary.",
                "confidence": "medium",
                "recommendations": [RECOMMENDATION_TEMPLATE],
                "tool_requests": [],
                "missing_evidence": [],
                "next_best_action": "build_agent_review_patch_plan.py",
            },
            "minimum_valid_response_when_blocked": {
                "summary": "One sentence blocker summary.",
                "confidence": "low",
                "recommendations": [],
                "tool_requests": [TOOL_REQUEST_TEMPLATE],
                "missing_evidence": ["specific missing evidence"],
                "next_best_action": "run requested broker tools, then retry schema-valid recommendation generation",
            },
        },
        "decision": {
            "schema_repair_required": True,
            "manual_review_required": True,
            "feed_into_next_provider_round": True,
            "tools_already_executed": has_runtime_evidence,
            "expected_next_layer": "schema-valid recommendations or broker-compatible tool_requests",
        },
        "guardrails": {
            "report_only": True,
            "patch_application_performed": False,
            "provider_execution_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "blender_runtime_touched": False,
        },
    }


def build_schema_repair_context_stack(
    *,
    base_context_reports: list[dict[str, Any]],
    rounds: list[dict[str, Any]],
    evidence_ready_for_manual_patch_count: int,
    provider: str,
) -> list[dict[str, Any]]:
    """Return context reports with one fresh schema-repair report appended."""

    clean = [
        item
        for item in base_context_reports
        if not (isinstance(item, dict) and item.get("kind") == SCHEMA_REPAIR_CONTEXT_KIND)
    ]
    if not should_emit_schema_repair_context(
        rounds=rounds,
        context_reports=clean,
        evidence_ready_for_manual_patch_count=evidence_ready_for_manual_patch_count,
    ):
        return clean
    clean.append(
        build_schema_repair_context_report(
            provider=provider,
            rounds=rounds,
            context_reports=clean,
            evidence_ready_for_manual_patch_count=evidence_ready_for_manual_patch_count,
        )
    )
    return clean
def should_attempt_schema_repair_retry(
    *,
    parsed_response: dict[str, Any],
    parse_diagnostics: dict[str, Any],
    evidence_ready_for_manual_patch_count: int,
    valid_tool_request_count: int = 0,
) -> bool:
    """Return true when a repair-only provider pass is worth attempting."""

    if valid_tool_request_count > 0:
        return False
    if not isinstance(parsed_response, dict):
        return True
    recommendations = parsed_response.get("recommendations")
    if isinstance(recommendations, list) and recommendations:
        return False

    if parse_diagnostics.get("context_echo_detected"):
        return True
    if not parse_diagnostics.get("json_ok", True):
        return True
    if parse_diagnostics.get("model_output_schema_mismatch") or not parse_diagnostics.get("schema_ok", False):
        return True
    reason = str(parse_diagnostics.get("empty_recommendations_reason") or parse_diagnostics.get("contract_empty_recommendations_reason") or "")
    if reason in SCHEMA_REPAIR_TRIGGER_REASONS:
        return True
    return evidence_ready_for_manual_patch_count > 0


def build_schema_repair_retry_prompt(
    *,
    provider: str,
    round_index: int,
    objective: str,
    raw_response: str,
    parsed_response: dict[str, Any],
    parse_diagnostics: dict[str, Any],
    context_reports: list[dict[str, Any]],
    rounds: list[dict[str, Any]],
    evidence_ready_for_manual_patch_count: int,
) -> str:
    """Build a strict repair-only prompt for a schema-mismatched provider reply."""

    runtime_evidence = collect_recent_runtime_tool_evidence(context_reports, max_reports=8, max_results_per_report=6)
    round_failures = summarize_round_schema_failures(rounds)
    payload = {
        "kind": "schema_repair_retry_prompt",
        "provider": provider,
        "round_index": round_index,
        "objective": objective,
        "task": "Repair the previous provider response into one valid JSON object only.",
        "hard_rules": [
            "Return JSON only: no Markdown, no prose, no fenced code block.",
            "Use exactly the required top-level keys.",
            "Do not echo files, docs, tool reports, or context previews.",
            "If runtime evidence is enough, produce at least one ready_for_patch_plan recommendation.",
            "If runtime evidence is not enough, recommendations must be empty and tool_requests or missing_evidence must explain the blocker.",
            "Do not request shell, git write, patch application, Blender runtime, provider execution, or persistent memory writes.",
            "Every recommendation must be small, manually reviewable, evidence-backed and non-destructive.",
        ],
        "required_top_level_keys": REQUIRED_TOP_LEVEL_KEYS,
        "recommendation_template": RECOMMENDATION_TEMPLATE,
        "tool_request_template": TOOL_REQUEST_TEMPLATE,
        "minimum_valid_response_when_ready": {
            "summary": "One sentence technical summary.",
            "confidence": "medium",
            "recommendations": [RECOMMENDATION_TEMPLATE],
            "tool_requests": [],
            "missing_evidence": [],
            "next_best_action": "build_agent_review_patch_plan.py",
        },
        "minimum_valid_response_when_blocked": {
            "summary": "One sentence blocker summary.",
            "confidence": "low",
            "recommendations": [],
            "tool_requests": [TOOL_REQUEST_TEMPLATE],
            "missing_evidence": ["specific missing evidence"],
            "next_best_action": "run requested broker tools, then retry schema-valid recommendation generation",
        },
        "evidence_ready_for_manual_patch_count": evidence_ready_for_manual_patch_count,
        "parse_diagnostics": {
            "json_ok": parse_diagnostics.get("json_ok"),
            "schema_ok": parse_diagnostics.get("schema_ok"),
            "schema_errors": parse_diagnostics.get("schema_errors", []),
            "context_echo_detected": parse_diagnostics.get("context_echo_detected"),
            "model_output_schema_mismatch": parse_diagnostics.get("model_output_schema_mismatch"),
            "empty_recommendations_reason": parse_diagnostics.get("empty_recommendations_reason") or parse_diagnostics.get("contract_empty_recommendations_reason"),
        },
        "round_failures": round_failures,
        "runtime_tool_evidence": runtime_evidence,
        "bad_response": {
            "raw_preview": raw_response[:4000],
            "parsed_keys": sorted(parsed_response.keys()) if isinstance(parsed_response, dict) else [],
            "parsed_response": parsed_response,
        },
        "output_contract": {
            "summary": "string",
            "confidence": "low|medium|high",
            "recommendations": [RECOMMENDATION_TEMPLATE],
            "tool_requests": [TOOL_REQUEST_TEMPLATE],
            "missing_evidence": ["string"],
            "next_best_action": "string",
        },
    }
    import json

    return (
        "You are a strict JSON repair adapter inside IA-Carmine. "
        "Repair the previous provider response into schema-valid planner JSON. "
        "Do not perform new analysis beyond the supplied evidence.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def summarize_schema_repair_retry(attempt: dict[str, Any]) -> dict[str, Any]:
    """Return compact telemetry for a repair attempt."""

    return {
        "attempted": bool(attempt.get("attempted")),
        "accepted": bool(attempt.get("accepted")),
        "reason": attempt.get("reason", ""),
        "json_ok": attempt.get("parse_diagnostics", {}).get("json_ok"),
        "schema_ok": attempt.get("parse_diagnostics", {}).get("schema_ok"),
        "recommendation_count": attempt.get("recommendation_diagnostics", {}).get("recommendation_count", 0),
        "valid_tool_request_count": attempt.get("parse_diagnostics", {}).get("valid_tool_request_count", 0),
        "empty_recommendations_reason": attempt.get("recommendation_diagnostics", {}).get("empty_recommendations_reason", ""),
    }
