#!/usr/bin/env python3
"""Report and selected-chunks summarizers for GitHub evidence bundles."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Tools.ai.github_evidence_bundle_io import (
    DEFAULT_SELECTED_CHUNKS_EVIDENCE,
    MAX_PATCH_PLAN_TEXT_CHARS,
    compact_value,
    repo_relative,
    read_json,
    resolve_repo_path,
    split_path_values,
)

CORE_SUMMARY_KEYS = (
    "usable_lanes",
    "unusable_lanes",
    "primary_advisory_provider",
    "policy",
    "mode",
    "provider",
    "python_exe",
    "device",
    "model_dir",
    "proposal_count",
    "patch_plan_count",
    "fallback_used",
    "manual_review_required",
    "recommendation_count",
    "round_count",
    "empty_recommendations_reason",
    "evidence_ready_for_manual_patch_count",
    "recommended_next_layer",
)
CHECK_SUMMARY_KEYS = (
    "classification",
    "usable_for_advisory",
    "npu_usable_for_advisory",
    "npu_classification",
    "metrics",
    "npu_metrics",
    "provider_envelope",
    "promotion_gate",
    "required_promotion_gate",
)


def compact_patch_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return compact patch-plan metadata for bundle summaries."""
    return {
        "id": plan.get("id"),
        "area": plan.get("area"),
        "source": plan.get("source"),
        "risk": plan.get("risk"),
        "status": plan.get("status"),
        "target_files": compact_value(plan.get("target_files") or [], max_string=300),
        "rationale": compact_value(plan.get("rationale") or "", max_string=MAX_PATCH_PLAN_TEXT_CHARS),
        "edit_strategy": compact_value(plan.get("edit_strategy") or "", max_string=MAX_PATCH_PLAN_TEXT_CHARS),
        "validation_commands": compact_value(plan.get("validation_commands") or [], max_string=500),
        "stop_conditions": compact_value(plan.get("stop_conditions") or [], max_string=500),
        "manual_review_required": plan.get("manual_review_required"),
    }


def summarize_patch_plan_report(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return native patch-plan summary for legacy agent_review_patch_plan reports."""
    if data.get("kind") != "agent_review_patch_plan":
        return None

    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    patch_plans = data.get("patch_plans") if isinstance(data.get("patch_plans"), list) else []

    return {
        "patch_plan_count": data.get("patch_plan_count", len(patch_plans)),
        "fallback_used": decision.get("fallback_used"),
        "manual_review_required": decision.get("manual_review_required"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "patch_application_performed": data.get("patch_application_performed"),
        "source_writes_performed": data.get("source_writes_performed"),
        "plans": [compact_patch_plan(plan) for plan in patch_plans if isinstance(plan, dict)],
    }


def add_core_summary_fields(summary: dict[str, Any], data: dict[str, Any]) -> None:
    """Add common scalar/list report fields to a summary."""
    for key in CORE_SUMMARY_KEYS:
        if key in data:
            summary[key] = compact_value(data.get(key))


def add_nested_summary_fields(summary: dict[str, Any], data: dict[str, Any]) -> None:
    """Add compact nested report fields to a summary."""
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    if checks:
        summary["checks"] = compact_value({key: checks.get(key) for key in CHECK_SUMMARY_KEYS if key in checks}, max_string=350)
    routing = data.get("routing") if isinstance(data.get("routing"), dict) else {}
    if routing:
        summary["routing"] = compact_value(
            {
                "advisory_lanes": routing.get("advisory_lanes"),
                "excluded_advisory_lanes": routing.get("excluded_advisory_lanes"),
                "primary_advisory_provider": routing.get("primary_advisory_provider"),
                "trusted_context_files": routing.get("trusted_context_files"),
                "excluded_context_files": routing.get("excluded_context_files"),
            },
            max_string=350,
        )
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    if context:
        summary["context"] = compact_value(
            {
                "context_files": context.get("context_files"),
                "excluded_context_files": context.get("excluded_context_files"),
                "advisory_context_routing": context.get("advisory_context_routing"),
            },
            max_string=350,
        )
    ollama = data.get("ollama") if isinstance(data.get("ollama"), dict) else {}
    if ollama:
        summary["ollama"] = compact_value(
            {"used": ollama.get("used"), "model": ollama.get("model"), "error": ollama.get("error"), "text_preview": (ollama.get("text") or "")[:500]},
            max_string=500,
        )


def base_report_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Return common report summary fields."""
    return {
        "schema_version": data.get("schema_version"),
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "patch_application_performed": data.get("patch_application_performed"),
        "source_writes_performed": data.get("source_writes_performed"),
        "errors": compact_value(data.get("errors") or []),
        "warnings": compact_value(data.get("warnings") or []),
    }


def summarize_report(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize one JSON validation/provider/report artifact."""
    rel = repo_relative(path, repo_root)
    data = read_json(path)
    if data is None:
        return {"path": rel, "exists": path.exists(), "json_ok": False, "kind": None, "passed": None, "summary": {}}

    summary = base_report_summary(data)
    add_core_summary_fields(summary, data)
    add_nested_summary_fields(summary, data)

    patch_plan_summary = summarize_patch_plan_report(data)
    if patch_plan_summary:
        summary["patch_plan_summary"] = patch_plan_summary

    return {"path": rel, "exists": True, "json_ok": True, "kind": data.get("kind"), "passed": data.get("passed"), "summary": summary}


def summarize_selected_chunks_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    """Return compact selected-chunks evidence without reading raw context packs."""
    rel = repo_relative(path, repo_root)
    data = read_json(path)
    if data is None:
        return {"path": rel, "exists": path.exists(), "json_ok": False, "kind": None, "passed": None, "summary": {}}

    summary: dict[str, Any] = {
        "schema_version": data.get("schema_version"),
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "source_writes_performed": data.get("source_writes_performed"),
        "selected_count": data.get("selected_count"),
        "total_selected_chars": data.get("total_selected_chars"),
        "max_chunks": data.get("max_chunks"),
        "max_total_chars": data.get("max_total_chars"),
        "source_bundle": data.get("source_bundle"),
        "source_chunks": data.get("source_chunks"),
        "decision": compact_value(data.get("decision") or {}),
        "errors": compact_value(data.get("errors") or []),
        "warnings": compact_value(data.get("warnings") or []),
    }
    return {"path": rel, "exists": True, "json_ok": True, "kind": data.get("kind"), "passed": data.get("passed"), "summary": summary}


def discover_selected_chunks_evidence(repo_root: Path, explicit_paths: list[str], *, auto_discover: bool = True) -> list[Path]:
    """Discover compact selected-chunks evidence files under docs evidence."""
    candidates = split_path_values(explicit_paths)
    if auto_discover and not candidates:
        candidates = list(DEFAULT_SELECTED_CHUNKS_EVIDENCE)
        evidence_dir = repo_root / "docs" / "LOCAL_VALIDATION_EVIDENCE"
        if evidence_dir.exists():
            for path in sorted(evidence_dir.glob("*selected_chunks_evidence.json")):
                rel = repo_relative(path, repo_root)
                if rel not in candidates:
                    candidates.append(rel)
    resolved: list[Path] = []
    seen: set[str] = set()
    for raw in candidates:
        path = resolve_repo_path(repo_root, raw)
        key = path.resolve().as_posix() if path.exists() else path.as_posix()
        if key not in seen and path.exists():
            resolved.append(path)
            seen.add(key)
    return resolved


def report_summaries(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return summary dicts from report entries."""
    return [item.get("summary", {}) for item in reports if isinstance(item.get("summary"), dict)]
