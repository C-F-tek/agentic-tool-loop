#!/usr/bin/env python3
"""Validate report-only selective execution plan artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_KIND = "selective_execution_plan"
REPORT_KIND = "selective_execution_plan_validation"
EXPECTED_SCHEMA_VERSION = 1

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a stable repo-relative POSIX path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    """Resolve value under repo_root unless already absolute."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON object from path."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, f"not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"read error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def validate_plan(path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate one selective execution plan."""
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    rel_path = repo_relative(path, repo_root)
    if data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "passed": False,
            "errors": [parse_error] if parse_error else ["failed to read plan"],
            "warnings": warnings,
        }

    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("apply_mode") != "report_only":
        errors.append("apply_mode must be report_only")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("patch_application_performed") is not False:
        errors.append("patch_application_performed must be false")
    if not _is_bool(data.get("passed")):
        errors.append("passed must be a boolean")
    if not isinstance(data.get("errors"), list):
        errors.append("errors must be a list")
    if not isinstance(data.get("warnings"), list):
        errors.append("warnings must be a list")

    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("inputs must be an object")
        inputs = {}
    for key in (
        "context_pack_evidence",
        "dry_run_matrix_evidence",
        "latest_gpu_npu_evidence",
        "validation_report_contract",
        "execution_plan_status",
        "tech_debt_tracker",
    ):
        if key not in inputs:
            errors.append(f"inputs.{key} missing")

    provider = data.get("provider_evidence_summary")
    if not isinstance(provider, dict):
        errors.append("provider_evidence_summary must be an object")
        provider = {}
    else:
        if provider.get("provider_execution_seen") is not True:
            warnings.append("provider evidence does not show real provider execution")
        if provider.get("ollama_gpu_primary_advisory") is not True:
            warnings.append("Ollama/GPU primary advisory decision is not true")
        if provider.get("npu_excluded_when_unusable") is not True:
            warnings.append("NPU exclusion decision is not true")

    dry_run = data.get("dry_run_summary")
    if not isinstance(dry_run, dict):
        errors.append("dry_run_summary must be an object")
        dry_run = {}
    else:
        if dry_run.get("provider_execution_performed") is not False:
            errors.append("dry_run_summary.provider_execution_performed must be false")
        if dry_run.get("all_steps_planned_only") is not True:
            errors.append("dry_run_summary.all_steps_planned_only must be true")

    validators = data.get("recommended_validators")
    if not isinstance(validators, list) or not validators:
        errors.append("recommended_validators must be a non-empty list")
        validators = []
    else:
        names: list[str] = []
        for index, item in enumerate(validators):
            if not isinstance(item, dict):
                errors.append(f"recommended_validators[{index}] must be an object")
                continue
            name = item.get("name")
            if _is_non_empty_string(name):
                names.append(str(name))
            else:
                errors.append(f"recommended_validators[{index}].name must be a non-empty string")
            if not _is_non_empty_string(item.get("command")):
                errors.append(f"recommended_validators[{index}].command must be a non-empty string")
            if item.get("provider_execution_performed") is not False:
                errors.append(f"recommended_validators[{index}].provider_execution_performed must be false")
        for required in ("python_syntax", "selective_execution_plan", "validation_report_contract"):
            if required not in names:
                errors.append(f"recommended_validators missing {required}")

    patch_specs = data.get("recommended_patch_specs")
    if not isinstance(patch_specs, list) or not patch_specs:
        errors.append("recommended_patch_specs must be a non-empty list")
        patch_specs = []
    else:
        for index, item in enumerate(patch_specs):
            if not isinstance(item, dict):
                errors.append(f"recommended_patch_specs[{index}] must be an object")
                continue
            if not _is_non_empty_string(item.get("id")):
                errors.append(f"recommended_patch_specs[{index}].id must be a non-empty string")
            if item.get("apply_mode") != "manual_review_only":
                errors.append(f"recommended_patch_specs[{index}].apply_mode must be manual_review_only")
            if item.get("provider_execution_performed") is not False:
                errors.append(f"recommended_patch_specs[{index}].provider_execution_performed must be false")
            if item.get("patch_application_performed") is not False:
                errors.append(f"recommended_patch_specs[{index}].patch_application_performed must be false")
            targets = item.get("target_files")
            if not isinstance(targets, list) or not targets:
                errors.append(f"recommended_patch_specs[{index}].target_files must be a non-empty list")
            elif any(not _is_non_empty_string(target) for target in targets):
                errors.append(f"recommended_patch_specs[{index}].target_files must contain only strings")

    for list_key in (
        "blocked_actions",
        "local_only_actions_for_carmine",
        "github_only_actions_for_ai",
        "risks",
    ):
        if not isinstance(data.get(list_key), list):
            errors.append(f"{list_key} must be a list")

    commands = data.get("next_command_set")
    if not isinstance(commands, dict) or not commands:
        errors.append("next_command_set must be a non-empty object")
    else:
        if "real_gpu_npu_evidence_for_carmine" not in commands:
            errors.append("next_command_set.real_gpu_npu_evidence_for_carmine missing")
        for key, value in commands.items():
            if not isinstance(value, list) or not value:
                errors.append(f"next_command_set.{key} must be a non-empty list")
            elif any(not _is_non_empty_string(command) for command in value):
                errors.append(f"next_command_set.{key} must contain only non-empty strings")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "passed": not errors,
        "plan_passed": data.get("passed"),
        "recommended_validator_count": len(validators),
        "recommended_patch_spec_count": len(patch_specs),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--plan", default="output/ai_pipeline/selective_execution_plan.json")
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan_path = resolve_repo_path(repo_root, args.plan)
    result = validate_plan(plan_path, repo_root)
    errors = [f"{result['path']}: {error}" for error in result.get("errors", [])]
    warnings = [f"{result['path']}: {warning}" for warning in result.get("warnings", [])]
    report = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "results": [result],
    }

    text = write_json_report(report, resolve_output_path(repo_root, args.output) if args.output else None)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
