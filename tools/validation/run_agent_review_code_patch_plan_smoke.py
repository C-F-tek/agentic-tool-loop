#!/usr/bin/env python3
"""Validate agent-review code patch-plan reports.

This smoke validator is report-only. It validates the proposed future
`agent_review_code_patch_plan` contract without applying patches, executing
providers, running Blender or writing source files.
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
    normalize_repo_path,
    read_json_object,
    report_guardrail_errors,
    report_only_guardrails,
    resolve_output_path,
    target_path_errors,
    write_json_report,
)


REPORT_KIND = "agent_review_code_patch_plan_smoke"
EXPECTED_PLAN_KIND = "agent_review_code_patch_plan"
EXPECTED_APPLY_MODE = "report_only_manual_review_code_patch_plan"
REQUIRED_PLAN_STRINGS = ("id", "area", "risk", "status", "rationale", "edit_strategy")
REQUIRED_PLAN_LISTS = ("validation_commands", "stop_conditions")


def validate_required_strings(item: dict[str, Any]) -> list[str]:
    """Validate required non-empty string fields on a plan item."""
    return [f"missing or invalid string field: {field}" for field in REQUIRED_PLAN_STRINGS if not isinstance(item.get(field), str) or not item.get(field)]


def validate_non_empty_string_list(item: dict[str, Any], field: str) -> list[str]:
    """Validate a non-empty list of non-empty strings."""
    value = item.get(field)
    if not isinstance(value, list) or not value:
        return [f"{field} must be a non-empty list"]
    if not all(isinstance(entry, str) and entry.strip() for entry in value):
        return [f"{field} entries must be non-empty strings"]
    return []


def plan_id_for(item: dict[str, Any], index: int) -> str:
    """Return the display id for a plan check."""
    return str(item.get("id") or f"<missing-{index}>")


def invalid_plan_check(index: int) -> dict[str, Any]:
    """Return the legacy check payload for a non-object plan item."""
    return {"index": index, "id": f"<invalid-{index}>", "ok": False, "errors": ["plan item must be an object"], "warnings": []}


def validate_target_files(repo_root: Path, item: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Validate plan target_files and return errors, warnings and normalized paths."""
    errors: list[str] = []
    warnings: list[str] = []
    normalized_targets: list[str] = []
    target_files = item.get("target_files")
    if not isinstance(target_files, list) or not target_files:
        return ["target_files must be a non-empty list"], warnings, normalized_targets

    for target in target_files:
        if not isinstance(target, str) or not target.strip():
            errors.append("target_files entries must be non-empty strings")
            continue
        normalized = normalize_repo_path(target)
        normalized_targets.append(normalized)
        path_errors = target_path_errors(repo_root, normalized, require_existing=False, require_code_like=False)
        errors.extend(f"{normalized}: {error}" for error in path_errors)
        if not (repo_root / normalized).exists():
            warnings.append(f"target file does not currently exist: {normalized}")
    return errors, warnings, normalized_targets


def validate_proposed_patch(item: dict[str, Any]) -> list[str]:
    """Validate proposed_patch metadata remains a string and has no forbidden raw target hints."""
    proposed_patch = item.get("proposed_patch", "")
    if proposed_patch is not None and not isinstance(proposed_patch, str):
        return ["proposed_patch must be a string when present"]
    if not isinstance(proposed_patch, str):
        return []
    errors: list[str] = []
    normalized_patch = normalize_repo_path(proposed_patch)
    for prefix in ("output/", "renders/", "indexAI/code_chunks/", "indexAI/project_code_chunks/"):
        if prefix in normalized_patch:
            errors.append(f"proposed_patch references forbidden prefix: {prefix}")
    return errors


def validate_plan_item(repo_root: Path, item: Any, index: int) -> dict[str, Any]:
    """Validate one code patch-plan item."""
    if not isinstance(item, dict):
        return invalid_plan_check(index)

    plan_id = plan_id_for(item, index)
    errors = validate_required_strings(item)
    warnings: list[str] = []
    if item.get("manual_review_required") is not True:
        errors.append("manual_review_required must be true on each plan")

    target_errors, target_warnings, normalized_targets = validate_target_files(repo_root, item)
    errors.extend(target_errors)
    warnings.extend(target_warnings)
    for field in REQUIRED_PLAN_LISTS:
        errors.extend(validate_non_empty_string_list(item, field))
    errors.extend(validate_proposed_patch(item))

    return {
        "index": index,
        "id": plan_id,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "target_files": normalized_targets,
    }


def validate_plan_report_contract(data: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Validate top-level code patch-plan fields and return raw plan items."""
    if data.get("kind") != EXPECTED_PLAN_KIND:
        errors.append(f"kind must be {EXPECTED_PLAN_KIND}")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append(f"apply_mode must be {EXPECTED_APPLY_MODE}")
    errors.extend(report_guardrail_errors(data, "code patch plan"))
    plans = data.get("code_patch_plans")
    if not isinstance(plans, list):
        errors.append("code_patch_plans must be a list")
        return []
    if data.get("patch_plan_count") != len(plans):
        errors.append("patch_plan_count must match len(code_patch_plans)")
    return plans


def validate_report(repo_root: Path, report_path: Path) -> dict[str, Any]:
    """Validate the code patch-plan report and return a smoke report."""
    data, load_errors = read_json_object(report_path)
    checks: list[dict[str, Any]] = []
    errors: list[str] = list(load_errors)
    warnings: list[str] = []

    if data:
        for index, item in enumerate(validate_plan_report_contract(data, errors)):
            check = validate_plan_item(repo_root, item, index)
            checks.append(check)
            errors.extend(f"{check['id']}: {error}" for error in check.get("errors", []))
            warnings.extend(f"{check['id']}: {warning}" for warning in check.get("warnings", []))

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "report": str(report_path),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "plan_count": len(checks),
        "checks": checks,
        "guardrails": report_only_guardrails(
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }


def resolve_report_path(repo_root: Path, report_value: str) -> Path:
    """Resolve a report path relative to the repository root."""
    path = Path(report_value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", default="Tools/ai/fixtures/agent_review_code_patch_plan_fixture.json")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = validate_report(repo_root, resolve_report_path(repo_root, args.report))
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
