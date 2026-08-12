#!/usr/bin/env python3
"""Decision helpers for GitHub validation evidence bundles."""
from __future__ import annotations

from typing import Any

from Tools.ai.github_evidence_bundle_io import as_list, list_contains
from Tools.ai.github_evidence_bundle_reports import report_summaries

NPU_UNUSABLE_CLASSIFICATIONS = {"unusable_output", "unusable"}
NPU_REAL_WORKLOAD_REPORT = "output/ai_packets/npu_real_workload_report.md"


def selected_chunks_evidence_seen(selected_chunks_evidence: list[dict[str, Any]]) -> bool:
    """Return whether at least one compact selected-chunks report is present."""
    return any(item.get("exists") is True and item.get("json_ok") is True for item in selected_chunks_evidence)


def selected_chunks_built(selected_chunks_evidence: list[dict[str, Any]]) -> bool:
    """Return whether selected chunk evidence shows a successful non-empty build."""
    for summary in report_summaries(selected_chunks_evidence):
        decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
        if decision.get("selected_chunks_built") is True:
            return True
        if isinstance(summary.get("selected_count"), int) and summary.get("selected_count", 0) > 0:
            return True
    return False


def selected_chunks_budget_respected(selected_chunks_evidence: list[dict[str, Any]]) -> bool:
    """Return whether selected-chunks evidence stayed within its character budget."""
    for summary in report_summaries(selected_chunks_evidence):
        decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
        if decision.get("budget_respected") is True:
            return True
        total_chars = summary.get("total_selected_chars")
        max_total_chars = summary.get("max_total_chars")
        if isinstance(total_chars, int) and isinstance(max_total_chars, int) and total_chars <= max_total_chars:
            return True
    return False


def npu_checks_mark_unusable(checks: dict[str, Any]) -> bool:
    """Return whether a checks block marks NPU as unusable for advisory."""
    if checks.get("npu_usable_for_advisory") is False:
        return True
    return str(checks.get("npu_classification") or "").lower() in NPU_UNUSABLE_CLASSIFICATIONS


def npu_marked_unusable(reports: list[dict[str, Any]]) -> bool:
    """Return whether validation evidence marks NPU output unusable for advisory."""
    for summary in report_summaries(reports):
        if list_contains(summary.get("unusable_lanes"), "npu"):
            return True
        checks = summary.get("checks") if isinstance(summary.get("checks"), dict) else {}
        if npu_checks_mark_unusable(checks):
            return True
    return False


def routing_excludes_npu(routing: dict[str, Any]) -> bool:
    """Return whether a routing block excludes NPU from advisory."""
    if list_contains(routing.get("excluded_advisory_lanes"), "npu"):
        return True
    return any(
        isinstance(ctx, dict) and ctx.get("lane") == "npu" and ctx.get("trusted") is False
        for ctx in as_list(routing.get("excluded_context_files"))
    )


def context_excludes_npu(context: dict[str, Any]) -> bool:
    """Return whether a context block excludes the NPU workload report."""
    excluded_context = context.get("excluded_context_files") or []
    if NPU_REAL_WORKLOAD_REPORT in excluded_context:
        return True
    advisory_routing = context.get("advisory_context_routing") if isinstance(context.get("advisory_context_routing"), dict) else {}
    return list_contains(advisory_routing.get("excluded_advisory_lanes"), "npu")


def npu_marked_excluded_from_advisory(reports: list[dict[str, Any]]) -> bool:
    """Return whether routing/evidence excludes NPU from advisory context."""
    for summary in report_summaries(reports):
        routing = summary.get("routing") if isinstance(summary.get("routing"), dict) else {}
        if routing_excludes_npu(routing):
            return True
        context = summary.get("context") if isinstance(summary.get("context"), dict) else {}
        if context_excludes_npu(context):
            return True
    return False


def npu_excluded_when_unusable(reports: list[dict[str, Any]]) -> bool:
    """Return whether evidence both marks NPU unusable and excludes it."""
    return npu_marked_unusable(reports) and npu_marked_excluded_from_advisory(reports)


def ollama_gpu_primary_advisory(reports: list[dict[str, Any]]) -> bool:
    """Return whether reports indicate Ollama/GPU as the primary advisory lane."""
    return any(
        (item.get("summary", {}).get("primary_advisory_provider", {}) or {}).get("provider") == "ollama"
        or (item.get("summary", {}).get("routing", {}).get("primary_advisory_provider", {}) or {}).get("provider") == "ollama"
        or (item.get("summary", {}).get("ollama", {}) or {}).get("used") is True
        for item in reports
    )


def npu_decode_smoke_passed(reports: list[dict[str, Any]]) -> bool:
    """Return whether a provider-executed NPU decode smoke diagnostic passed."""
    return any(
        item.get("kind") == "npu_decode_smoke_diagnostic"
        and item.get("passed") is True
        and item.get("summary", {}).get("provider_execution_performed") is True
        for item in reports
    )


def provider_execution_seen(reports: list[dict[str, Any]]) -> bool:
    """Return whether any summarized report performed provider execution."""
    return any(item.get("summary", {}).get("provider_execution_performed") is True for item in reports)


def patch_plan_summary_seen(reports: list[dict[str, Any]]) -> bool:
    """Return whether any summarized report contains native patch-plan details."""
    return any(bool(item.get("summary", {}).get("patch_plan_summary")) for item in reports)


def build_decision(
    reports: list[dict[str, Any]],
    selected_chunks_evidence: list[dict[str, Any]],
    artifact_manifest: list[dict[str, Any]],
    included_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the evidence bundle decision block."""
    return {
        "ollama_gpu_primary_advisory": ollama_gpu_primary_advisory(reports),
        "npu_excluded_when_unusable": npu_excluded_when_unusable(reports),
        "provider_execution_seen": provider_execution_seen(reports),
        "npu_decode_smoke_passed": npu_decode_smoke_passed(reports),
        "selected_chunks_evidence_seen": selected_chunks_evidence_seen(selected_chunks_evidence),
        "selected_chunks_built": selected_chunks_built(selected_chunks_evidence),
        "budget_respected": selected_chunks_budget_respected(selected_chunks_evidence),
        "artifact_manifest_built": bool(artifact_manifest),
        "included_artifacts_built": bool(included_artifacts),
        "included_artifact_count": len(included_artifacts),
        "patch_plan_summary_seen": patch_plan_summary_seen(reports),
    }
