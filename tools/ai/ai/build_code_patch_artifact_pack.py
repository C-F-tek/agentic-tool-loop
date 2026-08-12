#!/usr/bin/env python3
"""Build a compact artifact pack for code patch-plan reports.

This tool summarizes the report-only code patch-plan lane and its documentation
follow-up bridge without embedding large raw artifacts. It is designed to be fed
into the existing GitHub evidence bundle builder as a normal compact report.

It does not apply code patches, edit documentation, execute providers, run
Blender or write outside the requested report outputs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    compact_list,
    compact_text,
    now_iso,
    read_json_object,
    repo_rel,
    report_guardrail_errors,
    report_only_guardrails,
    resolve_output_path,
    write_json_and_markdown,
)


REPORT_KIND = "code_patch_artifact_pack"
DEFAULT_CODE_PATCH_PLAN = "output/patch_specs/agent_review_code_patch_plan_macro.json"
DEFAULT_DOCS_FOLLOWUP = "output/patch_specs/agent_review_code_docs_followup_macro.json"
DEFAULT_OUTPUT = "output/validation/code_patch_artifact_pack.json"
DEFAULT_MARKDOWN = "output/validation/code_patch_artifact_pack.md"


def nested_value(data: dict[str, Any], key: str) -> Any:
    """Return a nested source_evidence value from a plan object."""
    source = data.get("source_evidence")
    return source.get(key) if isinstance(source, dict) else None


def list_field_or_error(data: dict[str, Any], field: str, label: str, errors: list[str]) -> list[Any]:
    """Return a list field, appending the existing error wording when invalid."""
    value = data.get(field, [])
    if not isinstance(value, list):
        errors.append(f"{label} {field} must be a list")
        return []
    return value


def validate_count_matches(data: dict[str, Any], count_field: str, items: list[Any], label: str, errors: list[str]) -> None:
    """Append an error when a reported count does not match the list length."""
    if data.get(count_field) != len(items):
        errors.append(f"{label} {count_field} must match len({items_label_for_count(count_field)})")


def items_label_for_count(count_field: str) -> str:
    """Return the legacy list-field label used in count mismatch diagnostics."""
    return {
        "patch_plan_count": "code_patch_plans",
        "docs_followup_count": "docs_followup_suggestions",
    }.get(count_field, "items")


def summarize_code_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a compact code-plan summary safe for evidence bundles."""
    return {
        "id": plan.get("id"),
        "area": plan.get("area"),
        "risk": plan.get("risk"),
        "status": plan.get("status"),
        "target_files": compact_list(plan.get("target_files"), text_limit=250),
        "rationale": compact_text(plan.get("rationale")),
        "edit_strategy": compact_text(plan.get("edit_strategy")),
        "validation_commands": compact_list(plan.get("validation_commands"), text_limit=500),
        "stop_conditions": compact_list(plan.get("stop_conditions"), text_limit=500),
        "manual_review_required": plan.get("manual_review_required"),
        "source_evidence": {
            "contract": nested_value(plan, "contract"),
            "line_count_csv_hint": nested_value(plan, "line_count_csv_hint"),
        },
    }


def summarize_docs_followup(item: dict[str, Any]) -> dict[str, Any]:
    """Return a compact docs-follow-up summary safe for evidence bundles."""
    return {
        "id": item.get("id"),
        "source_code_patch_plan_id": item.get("source_code_patch_plan_id"),
        "area": item.get("area"),
        "risk": item.get("risk"),
        "status": item.get("status"),
        "target_files": compact_list(item.get("target_files"), text_limit=250),
        "missing_candidate_docs": compact_list(item.get("missing_candidate_docs"), text_limit=250),
        "rationale": compact_text(item.get("rationale")),
        "edit_strategy": compact_text(item.get("edit_strategy")),
        "validation_commands": compact_list(item.get("validation_commands"), text_limit=500),
        "stop_conditions": compact_list(item.get("stop_conditions"), text_limit=500),
        "manual_review_required": item.get("manual_review_required"),
    }


def summarize_code_plan_report(code_plan: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Validate and summarize an agent_review_code_patch_plan report."""
    if code_plan.get("kind") != "agent_review_code_patch_plan":
        errors.append("code patch plan kind must be agent_review_code_patch_plan")
    errors.extend(report_guardrail_errors(code_plan, "code patch plan"))
    raw_plans = list_field_or_error(code_plan, "code_patch_plans", "code patch plan", errors)
    if not raw_plans:
        return []
    validate_count_matches(code_plan, "patch_plan_count", raw_plans, "code patch plan", errors)
    return [summarize_code_plan(plan) for plan in raw_plans if isinstance(plan, dict)]


def summarize_docs_followup_report(docs_followup: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Validate and summarize an agent_review_code_docs_followup report."""
    if docs_followup.get("kind") != "agent_review_code_docs_followup":
        errors.append("docs follow-up kind must be agent_review_code_docs_followup")
    errors.extend(report_guardrail_errors(docs_followup, "docs follow-up"))
    raw_suggestions = list_field_or_error(docs_followup, "docs_followup_suggestions", "docs follow-up", errors)
    if not raw_suggestions:
        return []
    validate_count_matches(docs_followup, "docs_followup_count", raw_suggestions, "docs follow-up", errors)
    return [summarize_docs_followup(item) for item in raw_suggestions if isinstance(item, dict)]


def warn_unlinked_docs_followups(code_plan: dict[str, Any], docs_followup: dict[str, Any]) -> list[str]:
    """Warn when code plans have no matching docs-follow-up entry."""
    code_items = code_plan.get("code_patch_plans", [])
    docs_items = docs_followup.get("docs_followup_suggestions", [])
    if not isinstance(code_items, list) or not isinstance(docs_items, list):
        return []
    code_ids = {str(item.get("id")) for item in code_items if isinstance(item, dict)}
    docs_source_ids = {str(item.get("source_code_patch_plan_id")) for item in docs_items if isinstance(item, dict)}
    missing_docs = sorted(code_ids - docs_source_ids)
    if not missing_docs:
        return []
    return ["code plans without docs follow-up suggestions: " + ", ".join(missing_docs)]


def build_pack(repo_root: Path, code_plan_path: Path, docs_followup_path: Path) -> dict[str, Any]:
    """Build the compact artifact pack report."""
    errors: list[str] = []
    warnings: list[str] = []
    code_plan, code_errors = read_json_object(code_plan_path)
    docs_followup, docs_errors = read_json_object(docs_followup_path)
    errors.extend(f"code patch plan: {error}" for error in code_errors)
    errors.extend(f"docs follow-up: {error}" for error in docs_errors)

    code_plan_items = summarize_code_plan_report(code_plan, errors) if code_plan else []
    docs_followup_items = summarize_docs_followup_report(docs_followup, errors) if docs_followup else []
    if code_plan and docs_followup:
        warnings.extend(warn_unlinked_docs_followups(code_plan, docs_followup))

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "apply_mode": "report_only_compact_code_patch_artifact_pack",
        "inputs": {
            "code_patch_plan": repo_rel(repo_root, code_plan_path),
            "docs_followup": repo_rel(repo_root, docs_followup_path),
        },
        "summary": {
            "code_patch_plan_count": len(code_plan_items),
            "docs_followup_count": len(docs_followup_items),
            "code_patch_plan_ready": bool(code_plan_items) and not code_errors,
            "docs_followup_ready": bool(docs_followup_items) and not docs_errors,
        },
        "code_patch_plans": code_plan_items,
        "docs_followup_suggestions": docs_followup_items,
        "decision": {
            "ready_for_manual_code_review": bool(code_plan_items) and not errors,
            "ready_for_manual_docs_review": bool(docs_followup_items) and not errors,
            "manual_review_required": True,
            "recommended_next_layer": "review_code_and_docs_queues_together" if code_plan_items and docs_followup_items and not errors else "fix_or_collect_patch_plan_artifacts",
        },
        "guardrails": report_only_guardrails(
            docs_written=False,
            raw_patch_content_embedded=False,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the artifact pack as compact Markdown."""
    lines = ["# Code Patch Artifact Pack", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Manual review required: `{report['manual_review_required']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append(f"- Code patch plan count: `{report['summary']['code_patch_plan_count']}`")
    lines.append(f"- Docs follow-up count: `{report['summary']['docs_followup_count']}`")
    lines.append("")
    lines.extend(render_item_section("Code patch plans", report.get("code_patch_plans", []), "target_files"))
    lines.extend(render_item_section("Docs follow-up suggestions", report.get("docs_followup_suggestions", []), "target_files"))
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This pack is compact evidence only. It is not a patch apply queue.")
    return "\n".join(lines) + "\n"


def render_item_section(title: str, items: Any, target_key: str) -> list[str]:
    """Render repeated compact item sections."""
    lines = [f"## {title}", ""]
    if not items:
        return lines + ["- none", ""]
    for item in items:
        lines.append(f"### `{item.get('id')}`")
        if item.get("source_code_patch_plan_id"):
            lines.append(f"- Source code plan: `{item.get('source_code_patch_plan_id')}`")
        if item.get("area"):
            lines.append(f"- Area: `{item.get('area')}`")
        if item.get("risk"):
            lines.append(f"- Risk: `{item.get('risk')}`")
        if item.get("status"):
            lines.append(f"- Status: `{item.get('status')}`")
        lines.append(f"- Target files: `{item.get(target_key)}`")
        lines.append(f"- Rationale: {item.get('rationale')}")
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--code-patch-plan", default=DEFAULT_CODE_PATCH_PLAN)
    parser.add_argument("--docs-followup", default=DEFAULT_DOCS_FOLLOWUP)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    code_plan_path = resolve_output_path(repo_root, args.code_patch_plan)
    docs_followup_path = resolve_output_path(repo_root, args.docs_followup)
    report = build_pack(repo_root, code_plan_path, docs_followup_path)
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
