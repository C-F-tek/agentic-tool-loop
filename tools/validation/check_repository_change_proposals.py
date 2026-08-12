#!/usr/bin/env python3
"""Validate repository change proposal reports.

Proposal reports are advisory work products. This validator checks that they
remain manual-review-only, structurally useful for code/Markdown/JSON
suggestions, and separate from provider execution or source mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


EXPECTED_KIND = "repository_change_proposals"
EXPECTED_APPLY_MODE = "manual_review_only"

REQUIRED_ROOT_FIELDS = (
    "schema_version",
    "kind",
    "generated_at",
    "repo_root",
    "profile",
    "passed",
    "errors",
    "warnings",
    "apply_mode",
    "reports_read",
    "proposals",
)

REQUIRED_PROPOSAL_FIELDS = (
    "id",
    "priority",
    "area",
    "title",
    "rationale",
    "target_files",
    "change_type",
    "apply_mode",
    "patch_sketch",
    "validation_commands",
    "stop_conditions",
)

REQUIRED_SUGGESTION_OUTPUT_FIELDS = (
    "path",
    "artifact_kind",
    "operation",
    "content_status",
    "write_policy",
)

SUPPORTED_SUGGESTION_OUTPUT_KINDS = {
    "python_code",
    "markdown",
    "json",
    "powershell",
    "workflow_yaml",
    "path_group",
    "text_or_config",
}

FORBIDDEN_TARGET_PREFIXES = (
    "indexAI/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
)

FORBIDDEN_TARGET_EXACT = {
    "Scripting/shared/blender_compat.py",
}

FORBIDDEN_TARGET_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)

FORBIDDEN_COMMAND_FRAGMENTS = (
    "git reset --hard",
    "git clean",
    "Remove-Item -Recurse",
    "Remove-Item -Force -Recurse",
)


def split_path_values(items: list[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                values.append(normalized)
    return values


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_repo_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"expected a JSON object, got {type(data).__name__}"
    return data, None


def target_path_errors(path: str) -> list[str]:
    normalized = normalize_repo_path(path)
    errors: list[str] = []
    if normalized in FORBIDDEN_TARGET_EXACT:
        errors.append(f"forbidden target path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        errors.append(f"forbidden target prefix: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_TARGET_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON target: {normalized}")
    return errors


def validation_command_errors(command: Any) -> list[str]:
    text = str(command)
    lower = text.lower()
    errors: list[str] = []
    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        if fragment.lower() in lower:
            errors.append(f"forbidden destructive validation command fragment: {fragment}")
    return errors


def validate_suggestion_output(output: Any, *, proposal_id: str, index: int) -> dict[str, Any]:
    label = f"{proposal_id}.suggestion_outputs[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(output, dict):
        return {"label": label, "ok": False, "errors": [f"{label} must be an object"], "warnings": warnings}

    missing = [field for field in REQUIRED_SUGGESTION_OUTPUT_FIELDS if field not in output]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    artifact_kind = output.get("artifact_kind")
    if artifact_kind not in SUPPORTED_SUGGESTION_OUTPUT_KINDS:
        errors.append(f"unsupported artifact_kind: {artifact_kind}")
    if output.get("write_policy") != EXPECTED_APPLY_MODE:
        errors.append("write_policy must be manual_review_only")
    if output.get("operation") not in {"manual_patch_suggestion", "create_suggestion_file"}:
        warnings.append("operation should be manual_patch_suggestion or create_suggestion_file")

    path = normalize_repo_path(output.get("path"))
    for error in target_path_errors(path):
        errors.append(error)

    return {
        "label": label,
        "path": path,
        "artifact_kind": artifact_kind,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_proposal(item: Any, index: int) -> dict[str, Any]:
    proposal_id = f"proposals[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    suggestion_output_checks: list[dict[str, Any]] = []

    if not isinstance(item, dict):
        return {
            "id": proposal_id,
            "ok": False,
            "errors": [f"{proposal_id} must be an object"],
            "warnings": warnings,
            "suggestion_output_checks": suggestion_output_checks,
        }

    proposal_id = str(item.get("id") or proposal_id)
    missing = [field for field in REQUIRED_PROPOSAL_FIELDS if field not in item]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    if item.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("apply_mode must be manual_review_only")

    target_files = item.get("target_files")
    if not isinstance(target_files, list) or not all(isinstance(path, str) and path for path in target_files):
        errors.append("target_files must be a non-empty list of strings")
    else:
        for path in target_files:
            errors.extend(target_path_errors(path))

    for list_field in ("patch_sketch", "validation_commands", "stop_conditions"):
        value = item.get(list_field)
        if not isinstance(value, list) or not value:
            errors.append(f"{list_field} must be a non-empty list")

    validation_commands = item.get("validation_commands")
    if isinstance(validation_commands, list):
        for command in validation_commands:
            errors.extend(validation_command_errors(command))

    suggestion_outputs = item.get("suggestion_outputs")
    if suggestion_outputs is None:
        warnings.append("suggestion_outputs missing; report predates suggestion artifact descriptors")
    elif not isinstance(suggestion_outputs, list):
        errors.append("suggestion_outputs must be a list")
    else:
        for output_index, output in enumerate(suggestion_outputs):
            check = validate_suggestion_output(output, proposal_id=proposal_id, index=output_index)
            suggestion_output_checks.append(check)
            errors.extend(check.get("errors", []))
            warnings.extend(check.get("warnings", []))

    do_not_touch = item.get("do_not_touch")
    if do_not_touch is not None and not isinstance(do_not_touch, list):
        warnings.append("do_not_touch should be a list when present")

    return {
        "id": proposal_id,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "suggestion_output_count": len(suggestion_output_checks),
        "suggestion_output_checks": suggestion_output_checks,
    }


def validate_proposal_report(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return {
            "path": rel_path,
            "exists": False,
            "json_ok": False,
            "ok": False,
            "proposal_count": 0,
            "errors": ["proposal report is missing"],
            "warnings": warnings,
            "proposal_checks": [],
        }

    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": True,
            "json_ok": False,
            "ok": False,
            "proposal_count": 0,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "proposal_checks": [],
        }

    missing = [field for field in REQUIRED_ROOT_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required root fields: {', '.join(missing)}")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND!r}")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("root apply_mode must be manual_review_only")

    suggestion_contract = data.get("suggestion_contract")
    if suggestion_contract is None:
        warnings.append("suggestion_contract missing; report predates suggestion artifact descriptors")
    elif not isinstance(suggestion_contract, dict):
        errors.append("suggestion_contract must be an object")
    elif suggestion_contract.get("provider_execution_performed") is not False:
        errors.append("suggestion_contract.provider_execution_performed must be false")

    proposals = data.get("proposals")
    if not isinstance(proposals, list):
        errors.append("proposals must be a list")
        proposal_checks: list[dict[str, Any]] = []
    else:
        proposal_checks = [validate_proposal(item, index) for index, item in enumerate(proposals)]
        for check in proposal_checks:
            for error in check.get("errors", []):
                errors.append(f"{check.get('id')}: {error}")
            for warning in check.get("warnings", []):
                warnings.append(f"{check.get('id')}: {warning}")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "ok": not errors,
        "proposal_count": len(proposals) if isinstance(proposals, list) else 0,
        "errors": errors,
        "warnings": warnings,
        "proposal_checks": proposal_checks,
    }


def validate_repository_change_proposals(repo_root: Path, paths: list[Path]) -> dict[str, Any]:
    results = [validate_proposal_report(path, repo_root) for path in paths]
    errors = [
        f"{item['path']}: {error}"
        for item in results
        for error in item.get("errors", [])
    ]
    warnings = [
        f"{item['path']}: {warning}"
        for item in results
        for warning in item.get("warnings", [])
    ]
    return {
        "schema_version": 1,
        "kind": "repository_change_proposal_contract",
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "report_count": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--proposal",
        action="append",
        default=[],
        help="Proposal JSON path. Repeatable or comma-separated.",
    )
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    raw_paths = split_path_values(list(args.proposal or [])) or ["output/ai_pipeline/repository_change_proposals.json"]
    paths = [
        Path(raw).resolve() if Path(raw).is_absolute() else (repo_root / raw).resolve()
        for raw in raw_paths
    ]
    report = validate_repository_change_proposals(repo_root, paths)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
