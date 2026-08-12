#!/usr/bin/env python3
"""Markdown rendering helpers for GitHub evidence bundles."""
from __future__ import annotations

from typing import Any

REPORT_ENTRY_FIELDS = (
    ("provider_execution_performed", "Provider execution performed"),
    ("patch_application_performed", "Patch application performed"),
    ("source_writes_performed", "Source writes performed"),
    ("patch_plan_count", "Patch plan count"),
    ("recommendation_count", "Recommendation count"),
    ("recommended_next_layer", "Recommended next layer"),
    ("selected_count", "Selected count"),
    ("total_selected_chars", "Total selected chars"),
    ("max_total_chars", "Max total chars"),
    ("usable_lanes", "Usable lanes"),
    ("unusable_lanes", "Unusable lanes"),
    ("primary_advisory_provider", "Primary advisory provider"),
    ("python_exe", "Python executable"),
)
REPORT_DETAIL_FIELDS = (("errors", "Errors"), ("warnings", "Warnings"), ("routing", "Routing"), ("decision", "Decision"), ("ollama", "Ollama"))
PATCH_PLAN_SUMMARY_FIELDS = (
    ("patch_plan_count", "Patch plan count"),
    ("fallback_used", "Fallback used"),
    ("manual_review_required", "Manual review required"),
    ("provider_execution_performed", "Provider execution performed"),
    ("patch_application_performed", "Patch application performed"),
    ("source_writes_performed", "Source writes performed"),
)
PATCH_PLAN_DETAIL_FIELDS = (
    ("source", "Source"),
    ("risk", "Risk"),
    ("status", "Status"),
    ("target_files", "Target files"),
    ("rationale", "Rationale"),
    ("edit_strategy", "Strategy"),
)


def append_report_summary_fields(lines: list[str], summary: dict[str, Any]) -> None:
    """Append compact scalar/detail fields for a report summary."""
    for field, label in REPORT_ENTRY_FIELDS:
        if summary.get(field) is not None:
            lines.append(f"- {label}: `{summary.get(field)}`")
    for field, label in REPORT_DETAIL_FIELDS:
        if summary.get(field):
            lines.append(f"- {label}: `{summary.get(field)}`")


def append_patch_plan_summary_fields(lines: list[str], patch_plan_summary: dict[str, Any]) -> None:
    """Append scalar patch-plan summary fields."""
    for field, label in PATCH_PLAN_SUMMARY_FIELDS:
        lines.append(f"- {label}: `{patch_plan_summary.get(field)}`")


def append_patch_plan_detail_fields(lines: list[str], plan: dict[str, Any]) -> None:
    """Append one compact patch-plan item."""
    lines.append(f"#### {plan.get('id')} — {plan.get('area')}")
    for field, label in PATCH_PLAN_DETAIL_FIELDS:
        value = plan.get(field)
        if field in {"source", "risk", "status"}:
            lines.append(f"- {label}: `{value}`")
        else:
            lines.append(f"- {label}: {value}")
    lines.append("")


def render_report_entry(lines: list[str], item: dict[str, Any]) -> None:
    """Append one report/selected-chunks entry to Markdown lines."""
    summary = item.get("summary", {})
    lines.append(f"### `{item['path']}`")
    lines.append("")
    lines.append(f"- Exists: `{item['exists']}`")
    lines.append(f"- JSON OK: `{item['json_ok']}`")
    lines.append(f"- Kind: `{item.get('kind')}`")
    lines.append(f"- Passed: `{item.get('passed')}`")
    append_report_summary_fields(lines, summary)
    patch_plan_summary = summary.get("patch_plan_summary") or {}
    if patch_plan_summary:
        lines.append(f"- Patch plan summary count: `{patch_plan_summary.get('patch_plan_count')}`")
        lines.append(f"- Fallback used: `{patch_plan_summary.get('fallback_used')}`")
        lines.append(f"- Manual review required: `{patch_plan_summary.get('manual_review_required')}`")
    lines.append("")


def patch_plan_summary_entries(bundle: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return report entries that contain patch-plan summaries."""
    entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in bundle.get("reports", []):
        summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
        patch_plan_summary = summary.get("patch_plan_summary") if isinstance(summary.get("patch_plan_summary"), dict) else {}
        if patch_plan_summary:
            entries.append((item, patch_plan_summary))
    return entries


def render_patch_plan_summary(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append compact patch-plan summaries to Markdown lines."""
    entries = patch_plan_summary_entries(bundle)
    if not entries:
        return
    lines.append("## Patch plan summary")
    lines.append("")
    for item, patch_plan_summary in entries:
        lines.append(f"### `{item.get('path')}`")
        lines.append("")
        append_patch_plan_summary_fields(lines, patch_plan_summary)
        lines.append("")
        for plan in patch_plan_summary.get("plans", []):
            if isinstance(plan, dict):
                append_patch_plan_detail_fields(lines, plan)
        lines.append("")


def render_artifact_manifest(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append artifact manifest summary to Markdown lines."""
    manifest = bundle.get("artifact_manifest") or []
    if not manifest:
        return
    lines.append("## Artifact manifest")
    lines.append("")
    for item in manifest:
        if isinstance(item, dict):
            lines.append(f"- `{item.get('path')}` exists=`{item.get('exists')}` size=`{item.get('size_bytes')}` suffix=`{item.get('suffix')}` preview_chars=`{item.get('preview_chars')}`")
    lines.append("")


def render_included_artifacts(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append bounded included artifact contents to Markdown lines."""
    artifacts = bundle.get("included_artifacts") or []
    if not artifacts:
        return
    lines.append("## Included artifact contents")
    lines.append("")
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        lines.append(f"### `{item.get('path')}`")
        lines.append("")
        lines.append(f"- Role: `{item.get('role')}`")
        lines.append(f"- Exists: `{item.get('exists')}`")
        lines.append(f"- Suffix: `{item.get('suffix')}`")
        lines.append(f"- Size bytes: `{item.get('size_bytes')}`")
        lines.append(f"- SHA-256: `{item.get('sha256')}`")
        lines.append(f"- Content included: `{item.get('content_included')}`")
        lines.append(f"- Content truncated: `{item.get('content_truncated')}`")
        if item.get("skip_reason"):
            lines.append(f"- Skip reason: `{item.get('skip_reason')}`")
        if item.get("content"):
            lines.append("")
            lines.append("```text")
            lines.append(str(item.get("content")))
            lines.append("```")
        lines.append("")


def render_decision_summary(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append the top-level decision summary."""
    lines.append("## Decision summary")
    for key, value in bundle["decision"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")


def render_reports(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append report entries."""
    lines.append("## Reports")
    lines.append("")
    for item in bundle["reports"]:
        render_report_entry(lines, item)


def render_selected_chunks(lines: list[str], bundle: dict[str, Any]) -> None:
    """Append selected-chunks evidence entries when present."""
    selected = bundle.get("selected_chunks_evidence") or []
    if not selected:
        return
    lines.append("## Selected chunks evidence")
    lines.append("")
    for item in selected:
        render_report_entry(lines, item)


def render_git_push_helper(lines: list[str]) -> None:
    """Append the Git push helper block."""
    lines.append("## Git push helper")
    lines.append("")
    lines.append("```powershell")
    lines.append("git status --short")
    lines.append("# Replace <bundle_basename> with the generated evidence bundle basename.")
    lines.append("git add -- `")
    lines.append("  .\\docs\\LOCAL_VALIDATION_EVIDENCE\\<bundle_basename>.json `")
    lines.append("  .\\docs\\LOCAL_VALIDATION_EVIDENCE\\<bundle_basename>.md")
    lines.append('git commit -m "test: add local ai workflow evidence bundle"')
    lines.append("git push")
    lines.append("# Never use: git add docs/LOCAL_VALIDATION_EVIDENCE/")
    lines.append("```")


def render_markdown(bundle: dict[str, Any]) -> str:
    """Render the full evidence bundle Markdown companion."""
    lines = ["# Local Validation Evidence Bundle", ""]
    lines.append(f"- Generated at: `{bundle['generated_at']}`")
    lines.append(f"- Kind: `{bundle['kind']}`")
    lines.append("")
    render_decision_summary(lines, bundle)
    render_reports(lines, bundle)
    render_patch_plan_summary(lines, bundle)
    render_artifact_manifest(lines, bundle)
    render_included_artifacts(lines, bundle)
    render_selected_chunks(lines, bundle)
    render_git_push_helper(lines)
    return "\n".join(lines) + "\n"
