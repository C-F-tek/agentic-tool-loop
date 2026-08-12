#!/usr/bin/env python3
"""Validate report-only code edit proposal artifacts.

The validator checks the metadata contract for either:

- a direct `code_edit_proposal`; or
- a `code_edit_proposal_build` wrapper containing a nested `proposal` object.

It does not apply patches, execute providers, run Blender or write source files.
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
    ALLOWED_EDIT_KINDS,
    EDIT_KIND_STRUCTURED,
    EDIT_KIND_UNIFIED_DIFF,
    proposal_summary,
    validate_unified_diff_text,
)
from Tools.ai.code_patch_plan_common import (  # noqa: E402
    normalize_repo_path,
    read_json_object,
    report_guardrail_errors,
    report_only_guardrails,
    resolve_output_path,
    target_path_errors,
    write_json_report,
)

REPORT_KIND = "code_edit_proposal_smoke"
EXPECTED_KIND = "code_edit_proposal"
EXPECTED_APPLY_MODE = "report_only_manual_review_code_edit_proposal"
BUILD_WRAPPER_KIND = "code_edit_proposal_build"
REQUIRED_STRINGS = ("id", "target_file", "edit_kind", "rationale", "edit_strategy")
REQUIRED_LISTS = ("validation_commands", "stop_conditions")


def validate_required_strings(data: dict[str, Any]) -> list[str]:
    """Validate required non-empty string fields."""
    return [f"missing or invalid string field: {field}" for field in REQUIRED_STRINGS if not isinstance(data.get(field), str) or not data.get(field).strip()]


def validate_non_empty_string_list(data: dict[str, Any], field: str) -> list[str]:
    """Validate a required non-empty list of strings."""
    value = data.get(field)
    if not isinstance(value, list) or not value:
        return [f"{field} must be a non-empty list"]
    if not all(isinstance(item, str) and item.strip() for item in value):
        return [f"{field} entries must be non-empty strings"]
    return []


def unwrap_proposal(data: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str], str]:
    """Return a proposal object from direct or wrapper input."""
    errors: list[str] = []
    warnings: list[str] = []
    input_kind = str(data.get("kind") or "")
    if input_kind == EXPECTED_KIND:
        return data, errors, warnings, "direct_code_edit_proposal"
    if input_kind != BUILD_WRAPPER_KIND:
        errors.append(f"kind must be {EXPECTED_KIND} or {BUILD_WRAPPER_KIND}")
        return {}, errors, warnings, "unsupported_input"
    errors.extend(report_guardrail_errors(data, "code edit proposal build"))
    proposal = data.get("proposal")
    if not isinstance(proposal, dict) or not proposal:
        errors.append("code_edit_proposal_build.proposal must be a non-empty object")
        return {}, errors, warnings, "wrapper_missing_proposal"
    if data.get("passed") is not True:
        warnings.append("code_edit_proposal_build.passed is not true; validating nested proposal anyway")
    return proposal, errors, warnings, "code_edit_proposal_build_wrapper"


def validate_target(repo_root: Path, data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate target file metadata and repository path policy."""
    errors: list[str] = []
    warnings: list[str] = []
    target = normalize_repo_path(data.get("target_file"))
    errors.extend(f"{target}: {error}" for error in target_path_errors(repo_root, target))
    metadata = data.get("target_metadata")
    if not isinstance(metadata, dict):
        errors.append("target_metadata must be an object")
        return errors, warnings
    if normalize_repo_path(metadata.get("path")) != target:
        errors.append("target_metadata.path must match target_file")
    if metadata.get("exists") is not True:
        errors.append("target_metadata.exists must be true")
    if metadata.get("suffix") != Path(target).suffix.lower():
        errors.append("target_metadata.suffix must match target_file suffix")
    if metadata.get("sha256") is None:
        warnings.append("target_metadata.sha256 is null; regenerate proposal from local filesystem for stronger review evidence")
    if metadata.get("line_count") is None:
        warnings.append("target_metadata.line_count is null; regenerate proposal from local filesystem for stronger review evidence")
    return errors, warnings


def validate_edit_payload(data: dict[str, Any]) -> list[str]:
    """Validate edit-kind-specific payload."""
    errors: list[str] = []
    edit_kind = data.get("edit_kind")
    if edit_kind not in ALLOWED_EDIT_KINDS:
        errors.append(f"unsupported edit_kind: {edit_kind}")
        return errors
    structured_operations = data.get("structured_operations")
    unified_diff = data.get("unified_diff", "")
    if structured_operations is not None and not isinstance(structured_operations, list):
        errors.append("structured_operations must be a list when present")
    if unified_diff is not None and not isinstance(unified_diff, str):
        errors.append("unified_diff must be a string when present")
    if edit_kind == EDIT_KIND_STRUCTURED and not structured_operations:
        errors.append("structured_edit requires non-empty structured_operations")
    if edit_kind == EDIT_KIND_UNIFIED_DIFF:
        errors.extend(validate_unified_diff_text(str(unified_diff or ""), normalize_repo_path(data.get("target_file"))))
    return errors


def validate_proposal_metadata(data: dict[str, Any]) -> list[str]:
    """Validate proposal kind, mode, guardrails and required metadata fields."""
    errors: list[str] = []
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"proposal.kind must be {EXPECTED_KIND}")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append(f"proposal.apply_mode must be {EXPECTED_APPLY_MODE}")
    errors.extend(report_guardrail_errors(data, "code edit proposal"))
    errors.extend(validate_required_strings(data))
    for field in REQUIRED_LISTS:
        errors.extend(validate_non_empty_string_list(data, field))
    return errors


def validate_report(repo_root: Path, proposal_path: Path) -> dict[str, Any]:
    """Validate one code edit proposal artifact or build wrapper."""
    raw_data, load_errors = read_json_object(proposal_path)
    errors = list(load_errors)
    warnings: list[str] = []
    input_mode = "empty_or_unreadable"
    data: dict[str, Any] = {}
    if raw_data:
        data, unwrap_errors, unwrap_warnings, input_mode = unwrap_proposal(raw_data)
        errors.extend(unwrap_errors)
        warnings.extend(unwrap_warnings)
    if data:
        errors.extend(validate_proposal_metadata(data))
        target_errors, target_warnings = validate_target(repo_root, data)
        errors.extend(target_errors)
        warnings.extend(target_warnings)
        errors.extend(validate_edit_payload(data))
        if data.get("ready_for_manual_review") is not True:
            errors.append("ready_for_manual_review must be true")

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "proposal": str(proposal_path),
        "input_mode": input_mode,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "summary": proposal_summary(data) if data else {},
        "guardrails": report_only_guardrails(
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }


def resolve_input_path(repo_root: Path, value: str) -> Path:
    """Resolve input artifact path relative to the repository root."""
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--proposal", default="Tools/ai/fixtures/code_edit_proposal_fixture.json")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = validate_report(repo_root, resolve_input_path(repo_root, args.proposal))
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
