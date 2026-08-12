#!/usr/bin/env python3
"""Validate inert proposal-derived patch spec drafts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

EXPECTED_SPEC_KIND = "proposal_patch_spec_draft"
EXPECTED_MANIFEST_KIND = "proposal_patch_spec_manifest"
EXPECTED_APPLY_MODE = "manual_review_only"
EXPECTED_DRAFT_STATUS = "needs_concrete_replacements"

SUPPORTED_OUTPUT_KINDS = {
    "python_code",
    "markdown",
    "json",
    "powershell",
    "workflow_yaml",
    "text_or_config",
}

FORBIDDEN_TARGET_PREFIXES = (
    "indexAI/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
    "patch_specs/inbox/",
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
    "patch_specs/inbox/",
)

REQUIRED_SPEC_FIELDS = (
    "version",
    "schema_version",
    "kind",
    "generated_at",
    "source_proposal_report",
    "proposal_id",
    "apply_mode",
    "draft_status",
    "provider_execution_performed",
    "description",
    "operations",
)

REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "kind",
    "generated_at",
    "repo_root",
    "source_proposal_report",
    "output_dir",
    "passed",
    "errors",
    "warnings",
    "provider_execution_performed",
    "apply_mode",
    "draft_status",
    "patch_spec_count",
    "skipped_target_count",
    "specs",
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
    return str(value or "").strip().replace("\\", "/")


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


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


def target_path_errors(path: str, repo_root: Path) -> list[str]:
    normalized = normalize_repo_path(path)
    errors: list[str] = []
    if not normalized:
        return ["target path is empty"]
    if Path(normalized).is_absolute():
        errors.append("absolute target paths are not allowed")
    full = (repo_root / normalized).resolve()
    try:
        full.relative_to(repo_root)
    except ValueError:
        errors.append("target path escapes repository root")
    if normalized in FORBIDDEN_TARGET_EXACT:
        errors.append(f"forbidden target path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        errors.append(f"forbidden target prefix: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_TARGET_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON target: {normalized}")
    if "*" in normalized or normalized.endswith("/"):
        errors.append("target must be a concrete file, not a glob or directory")
    if not full.exists():
        errors.append("target file does not exist")
    elif not full.is_file():
        errors.append("target is not a file")
    return errors


def validation_command_errors(command: Any) -> list[str]:
    text = str(command)
    lower = text.lower()
    errors: list[str] = []
    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        if fragment.lower() in lower:
            errors.append(f"forbidden command fragment: {fragment}")
    return errors


def validate_operation(op: Any, index: int, repo_root: Path) -> dict[str, Any]:
    label = f"operations[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(op, dict):
        return {"label": label, "ok": False, "errors": [f"{label} must be an object"], "warnings": warnings}

    path = normalize_repo_path(op.get("path"))
    errors.extend(target_path_errors(path, repo_root))

    replacements = op.get("replacements")
    if not isinstance(replacements, list):
        errors.append("replacements must be a list")
    elif replacements:
        errors.append("draft replacements must be empty until a reviewed concrete patch is created")

    if op.get("draft_status") != EXPECTED_DRAFT_STATUS:
        errors.append(f"draft_status must be {EXPECTED_DRAFT_STATUS}")
    if not op.get("proposal_id"):
        errors.append("proposal_id is required")
    artifact_kind = op.get("artifact_kind")
    if artifact_kind not in SUPPORTED_OUTPUT_KINDS:
        errors.append(f"unsupported artifact_kind: {artifact_kind}")

    return {
        "label": label,
        "path": path,
        "artifact_kind": artifact_kind,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_spec(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []

    if rel_path.startswith("patch_specs/inbox/"):
        errors.append("draft spec is in the GitHub Action inbox queue")
    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "ok": False,
            "errors": errors + [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "operation_count": 0,
            "operation_checks": [],
        }

    missing = [field for field in REQUIRED_SPEC_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("kind") != EXPECTED_SPEC_KIND:
        errors.append(f"kind must be {EXPECTED_SPEC_KIND}")
    if int(data.get("version", 0) or 0) != 1:
        errors.append("version must be 1")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("apply_mode must be manual_review_only")
    if data.get("draft_status") != EXPECTED_DRAFT_STATUS:
        errors.append(f"draft_status must be {EXPECTED_DRAFT_STATUS}")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")

    operations = data.get("operations")
    if not isinstance(operations, list) or not operations:
        errors.append("operations must be a non-empty list")
        operation_checks: list[dict[str, Any]] = []
    else:
        operation_checks = [validate_operation(op, index, repo_root) for index, op in enumerate(operations)]
        for check in operation_checks:
            for error in check.get("errors", []):
                errors.append(f"{check.get('label')}: {error}")
            for warning in check.get("warnings", []):
                warnings.append(f"{check.get('label')}: {warning}")

    for list_field in ("validation_commands", "stop_conditions", "guardrails"):
        value = data.get(list_field)
        if value is not None and not isinstance(value, list):
            errors.append(f"{list_field} must be a list when present")

    validation_commands = data.get("validation_commands")
    if isinstance(validation_commands, list):
        for command in validation_commands:
            errors.extend(validation_command_errors(command))

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "proposal_id": data.get("proposal_id"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "operation_count": len(operations) if isinstance(operations, list) else 0,
        "operation_checks": operation_checks,
    }


def validate_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "spec_paths": [],
        }

    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("kind") != EXPECTED_MANIFEST_KIND:
        errors.append(f"kind must be {EXPECTED_MANIFEST_KIND}")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("apply_mode must be manual_review_only")
    if data.get("draft_status") != EXPECTED_DRAFT_STATUS:
        errors.append(f"draft_status must be {EXPECTED_DRAFT_STATUS}")

    specs = data.get("specs")
    spec_paths: list[str] = []
    if not isinstance(specs, list):
        errors.append("specs must be a list")
    else:
        for item in specs:
            if not isinstance(item, dict):
                errors.append("spec manifest entries must be objects")
                continue
            spec_path = normalize_repo_path(item.get("path"))
            if not spec_path:
                errors.append("spec manifest entry path is required")
                continue
            if spec_path.startswith("patch_specs/inbox/"):
                errors.append(f"manifest points to queued inbox spec: {spec_path}")
            spec_paths.append(spec_path)
    if isinstance(data.get("patch_spec_count"), int) and len(spec_paths) != data.get("patch_spec_count"):
        errors.append("patch_spec_count does not match specs length")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "spec_paths": spec_paths,
    }


def validate_patch_spec_drafts(repo_root: Path, manifest_paths: list[Path], spec_paths: list[Path]) -> dict[str, Any]:
    manifest_checks = [validate_manifest(path, repo_root) for path in manifest_paths]
    paths_from_manifests = [
        resolve_repo_path(repo_root, spec_path)
        for manifest in manifest_checks
        for spec_path in manifest.get("spec_paths", [])
    ]
    all_spec_paths = list(dict.fromkeys([*paths_from_manifests, *spec_paths]))
    spec_checks = [validate_spec(path, repo_root) for path in all_spec_paths]

    errors = [
        f"{item['path']}: {error}"
        for item in [*manifest_checks, *spec_checks]
        for error in item.get("errors", [])
    ]
    warnings = [
        f"{item['path']}: {warning}"
        for item in [*manifest_checks, *spec_checks]
        for warning in item.get("warnings", [])
    ]
    if not manifest_checks and not spec_checks:
        errors.append("no manifests or specs were provided")

    return {
        "schema_version": 1,
        "kind": "proposal_patch_spec_draft_contract",
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "manifest_count": len(manifest_checks),
        "spec_count": len(spec_checks),
        "manifest_checks": manifest_checks,
        "spec_checks": spec_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="Patch spec draft manifest path. Repeatable or comma-separated.",
    )
    parser.add_argument(
        "--spec",
        action="append",
        default=[],
        help="Patch spec draft JSON path. Repeatable or comma-separated.",
    )
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_paths = [
        resolve_repo_path(repo_root, raw)
        for raw in split_path_values(list(args.manifest or []))
    ]
    spec_paths = [
        resolve_repo_path(repo_root, raw)
        for raw in split_path_values(list(args.spec or []))
    ]
    if not manifest_paths and not spec_paths:
        manifest_paths = [repo_root / "output/patch_specs/proposal_patch_specs_manifest.json"]

    report = validate_patch_spec_drafts(repo_root, manifest_paths, spec_paths)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
