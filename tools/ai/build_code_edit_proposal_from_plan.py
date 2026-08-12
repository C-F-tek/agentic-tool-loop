#!/usr/bin/env python3
"""Build a report-only code edit proposal from a code patch-plan item.

This is the bridge from `agent_review_code_patch_plan` to a concrete
`code_edit_proposal` artifact. It does not apply patches, execute providers,
run Blender or write source files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_edit_proposal_helpers import (  # noqa: E402
    EDIT_KIND_NOOP,
    EDIT_KIND_STRUCTURED,
    EDIT_KIND_UNIFIED_DIFF,
    build_code_edit_proposal,
    proposal_summary,
)
from Tools.ai.code_patch_plan_common import (  # noqa: E402
    now_iso,
    read_json_object,
    report_guardrail_errors,
    report_only_guardrails,
    resolve_output_path,
    write_json_and_markdown,
)

REPORT_KIND = "code_edit_proposal_build"
EXPECTED_PLAN_KIND = "agent_review_code_patch_plan"
DEFAULT_CODE_PATCH_PLAN = "output/patch_specs/agent_review_code_patch_plan_macro.json"
DEFAULT_OUTPUT = "output/patch_specs/code_edit_proposal.json"
DEFAULT_MARKDOWN = "output/patch_specs/code_edit_proposal.md"


def find_plan_item(report: dict[str, Any], plan_id: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Return a selected plan item by id or the first ready plan."""
    plans = report.get("code_patch_plans")
    if not isinstance(plans, list):
        return None, ["code_patch_plans must be a list"]
    if not plans:
        return None, ["code_patch_plans is empty"]
    if plan_id:
        for item in plans:
            if isinstance(item, dict) and item.get("id") == plan_id:
                return item, []
        return None, [f"plan id not found: {plan_id}"]
    for item in plans:
        if isinstance(item, dict) and item.get("status") in {"ready_for_manual_review", "candidate_for_manual_review"}:
            return item, []
    for item in plans:
        if isinstance(item, dict):
            return item, []
    return None, ["no object plan item found"]


def infer_target_file(plan: dict[str, Any]) -> tuple[str, list[str]]:
    """Infer the primary target file from one code patch-plan item."""
    target_files = plan.get("target_files")
    if not isinstance(target_files, list) or not target_files:
        return "", ["selected plan has no target_files"]
    first = target_files[0]
    if not isinstance(first, str) or not first.strip():
        return "", ["selected plan primary target file is invalid"]
    if len(target_files) > 1:
        return first, ["selected plan has multiple target_files; using first target only"]
    return first, []


def infer_edit_payload(plan: dict[str, Any], edit_kind: str, unified_diff: str, structured_operation: list[dict[str, Any]] | None) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Return diff/operations payload for the proposal."""
    warnings: list[str] = []
    operations = structured_operation or []
    if edit_kind == EDIT_KIND_NOOP:
        return "", [], warnings
    if edit_kind == EDIT_KIND_UNIFIED_DIFF:
        if not unified_diff.strip():
            warnings.append("unified_diff edit requested without diff text; proposal will fail smoke until diff is supplied")
        return unified_diff, [], warnings
    if edit_kind == EDIT_KIND_STRUCTURED:
        if not operations:
            warnings.append("structured_edit requested without operations; proposal will fail smoke until operations are supplied")
        return "", operations, warnings
    warnings.append(f"unknown edit_kind passed to builder: {edit_kind}")
    return unified_diff, operations, warnings


def validate_source_plan_report(report: dict[str, Any]) -> list[str]:
    """Validate source code patch-plan report guardrails."""
    errors: list[str] = []
    if report.get("kind") != EXPECTED_PLAN_KIND:
        errors.append(f"code patch plan kind must be {EXPECTED_PLAN_KIND}")
    errors.extend(report_guardrail_errors(report, "code patch plan"))
    return errors


def plan_list_or_none(plan: dict[str, Any], field: str) -> list[Any] | None:
    """Return a list-valued plan field when present."""
    value = plan.get(field)
    return value if isinstance(value, list) else None


def proposal_id_for(plan: dict[str, Any]) -> str:
    """Return the generated proposal id for a selected plan."""
    return f"code_edit_from_{plan.get('id') or 'plan'}"


def build_report(
    repo_root: Path,
    source_path: Path,
    plan_report: dict[str, Any],
    plan_item: dict[str, Any] | None,
    proposal: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Build wrapper report around the generated proposal."""
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
        "apply_mode": "report_only_code_edit_proposal_build",
        "inputs": {
            "code_patch_plan": str(source_path),
            "source_kind": plan_report.get("kind"),
            "selected_plan_id": plan_item.get("id") if plan_item else None,
        },
        "selected_plan": plan_item or {},
        "proposal": proposal or {},
        "proposal_summary": proposal_summary(proposal) if proposal else {},
        "decision": {
            "ready_for_code_edit_proposal_smoke": bool(proposal) and not errors,
            "manual_review_required": True,
            "recommended_next_layer": "run_code_edit_proposal_smoke" if proposal and not errors else "fix_or_select_code_patch_plan",
        },
        "guardrails": report_only_guardrails(
            proposal_generated=True,
            proposal_applied=False,
            providers_executed=False,
            blender_runtime_executed=False,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render wrapper report and proposal summary."""
    lines = ["# Code Edit Proposal Build", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Manual review required: `{report['manual_review_required']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append(f"- Selected plan: `{report['inputs'].get('selected_plan_id')}`")
    lines.append("")
    summary = report.get("proposal_summary") or {}
    lines.append("## Proposal summary")
    lines.append("")
    if not summary:
        lines.append("- none")
    else:
        lines.append(f"- Target file: `{summary.get('target_file')}`")
        lines.append(f"- Edit kind: `{summary.get('edit_kind')}`")
        lines.append(f"- Ready for manual review: `{summary.get('ready_for_manual_review')}`")
        lines.append(f"- Target line count: `{summary.get('target_line_count')}`")
        lines.append(f"- Target SHA-256: `{summary.get('target_sha256')}`")
        lines.append(f"- Rationale: {summary.get('rationale')}")
        lines.append(f"- Strategy: {summary.get('edit_strategy')}")
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This build creates proposal metadata only. It does not apply the proposal.")
    return "\n".join(lines) + "\n"


def build_code_edit_from_plan(
    repo_root: Path,
    plan_path: Path,
    plan_id: str | None,
    edit_kind: str,
    unified_diff: str,
    structured_operations: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build one code edit proposal from a code patch plan."""
    plan_report, load_errors = read_json_object(plan_path)
    errors = [f"code patch plan: {error}" for error in load_errors]
    warnings: list[str] = []
    selected_plan: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    if plan_report:
        errors.extend(validate_source_plan_report(plan_report))
        selected_plan, select_errors = find_plan_item(plan_report, plan_id)
        errors.extend(select_errors)
    if selected_plan:
        target_file, target_warnings = infer_target_file(selected_plan)
        warnings.extend(target_warnings)
        diff_text, operations, payload_warnings = infer_edit_payload(selected_plan, edit_kind, unified_diff, structured_operations)
        warnings.extend(payload_warnings)
        if target_file:
            proposal, proposal_errors, proposal_warnings = build_code_edit_proposal(
                repo_root,
                proposal_id=proposal_id_for(selected_plan),
                target_file=target_file,
                rationale=str(selected_plan.get("rationale") or "Generated from code patch plan."),
                edit_strategy=str(selected_plan.get("edit_strategy") or "Review the source plan and apply a minimal manual edit."),
                edit_kind=edit_kind,
                unified_diff=diff_text,
                structured_operations=operations,
                validation_commands=plan_list_or_none(selected_plan, "validation_commands"),
                stop_conditions=plan_list_or_none(selected_plan, "stop_conditions"),
            )
            errors.extend(proposal_errors)
            warnings.extend(proposal_warnings)
    return build_report(repo_root, plan_path, plan_report, selected_plan, proposal, errors, warnings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--code-patch-plan", default=DEFAULT_CODE_PATCH_PLAN)
    parser.add_argument("--plan-id", help="Optional code_patch_plans[].id to select.")
    parser.add_argument("--edit-kind", choices=[EDIT_KIND_NOOP, EDIT_KIND_STRUCTURED, EDIT_KIND_UNIFIED_DIFF], default=EDIT_KIND_NOOP)
    parser.add_argument("--unified-diff", default="", help="Optional bounded unified diff text for unified_diff proposals.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan_path = resolve_output_path(repo_root, args.code_patch_plan)
    report = build_code_edit_from_plan(repo_root, plan_path, args.plan_id, args.edit_kind, args.unified_diff, None)
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
