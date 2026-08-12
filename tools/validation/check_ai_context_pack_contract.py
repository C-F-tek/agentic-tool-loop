#!/usr/bin/env python3
"""Validate AI context pack and compact evidence contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

PACK_KIND = "ai_context_pack"
EVIDENCE_KIND = "ai_context_pack_evidence"
REPORT_KIND = "ai_context_pack_contract"
EXPECTED_SCHEMA_VERSION = 1
EXPECTED_APPLY_MODE = "context_only"

FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    ".venv/",
    "__pycache__/",
    "indexAI/",
    "output/",
    "renders/",
    "venv/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
)

FORBIDDEN_PATH_EXACT = {
    "Scripting/shared/blender_compat.py",
}

FORBIDDEN_PATH_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)

FORBIDDEN_COMMAND_FRAGMENTS = (
    "git reset --hard",
    "git clean",
    "Remove-Item -Recurse",
    "Remove-Item -Force -Recurse",
    "patch_specs/inbox/",
    " --write",
)

REQUIRED_PACK_FIELDS = (
    "schema_version",
    "kind",
    "generated_at",
    "repo_root",
    "profile",
    "profile_description",
    "apply_mode",
    "provider_execution_performed",
    "passed",
    "errors",
    "warnings",
    "max_total_chars",
    "max_file_chars",
    "total_included_chars",
    "file_count",
    "included_file_count",
    "truncated_file_count",
    "validation_commands",
    "stop_conditions",
    "files",
)

REQUIRED_FILE_FIELDS = (
    "path",
    "role",
    "required",
    "exists",
    "included",
    "policy_ok",
    "size_bytes",
    "line_count",
    "sha256",
    "chars",
    "included_chars",
    "truncated",
    "content",
)

REQUIRED_EVIDENCE_FIELDS = (
    "schema_version",
    "kind",
    "generated_at",
    "repo_root",
    "profile",
    "source_pack",
    "passed",
    "errors",
    "warnings",
    "provider_execution_performed",
    "apply_mode",
    "file_count",
    "included_file_count",
    "truncated_file_count",
    "total_included_chars",
    "validation_command_count",
    "required_missing",
    "forbidden_path_count",
    "blender_runtime_touched",
    "included_paths",
    "decision",
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


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


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


def path_policy_errors(path: str) -> list[str]:
    normalized = normalize_repo_path(path)
    errors: list[str] = []
    if not normalized:
        return ["path is empty"]
    if Path(normalized).is_absolute():
        errors.append("absolute paths are not allowed")
    if normalized in FORBIDDEN_PATH_EXACT:
        errors.append(f"forbidden exact path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES):
        errors.append(f"forbidden path prefix: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_PATH_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON path: {normalized}")
    if "*" in normalized or normalized.endswith("/"):
        errors.append("context paths must be concrete files")
    return errors


def validation_command_errors(command: Any) -> list[str]:
    lower = str(command).lower()
    return [
        f"forbidden command fragment: {fragment}"
        for fragment in FORBIDDEN_COMMAND_FRAGMENTS
        if fragment.lower() in lower
    ]


def validate_file_entry(entry: Any, index: int) -> dict[str, Any]:
    label = f"files[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(entry, dict):
        return {
            "label": label,
            "path": label,
            "ok": False,
            "errors": [f"{label} must be an object"],
            "warnings": warnings,
        }

    missing = [field for field in REQUIRED_FILE_FIELDS if field not in entry]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    path = normalize_repo_path(entry.get("path"))
    errors.extend(path_policy_errors(path))

    for bool_field in ("required", "exists", "included", "policy_ok", "truncated"):
        if bool_field in entry and not isinstance(entry.get(bool_field), bool):
            errors.append(f"{bool_field} must be a boolean")
    if entry.get("policy_ok") is not True:
        errors.append(f"policy_ok must be true for included context paths: {entry.get('policy_error')}")
    if entry.get("required") is True and entry.get("included") is not True:
        errors.append("required context file must be included")
    if entry.get("included") is True and not isinstance(entry.get("content"), str):
        errors.append("included file content must be a string")
    if entry.get("included") is True and int(entry.get("included_chars") or 0) <= 0:
        errors.append("included file must have included_chars > 0")
    return {
        "label": label,
        "path": path,
        "role": entry.get("role"),
        "required": entry.get("required"),
        "included": entry.get("included"),
        "truncated": entry.get("truncated"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_pack(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "kind": None,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "profile": None,
            "file_count": 0,
            "file_checks": [],
        }

    missing = [field for field in REQUIRED_PACK_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("kind") != PACK_KIND:
        errors.append(f"kind must be {PACK_KIND}")
    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append(f"apply_mode must be {EXPECTED_APPLY_MODE}")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("passed") is not True:
        errors.append("context pack passed must be true")
    if not isinstance(data.get("errors"), list) or data.get("errors"):
        errors.append("context pack errors must be an empty list")
    if not isinstance(data.get("warnings"), list):
        errors.append("context pack warnings must be a list")

    validation_commands = data.get("validation_commands")
    if not isinstance(validation_commands, list) or not validation_commands:
        errors.append("validation_commands must be a non-empty list")
    else:
        for command in validation_commands:
            errors.extend(validation_command_errors(command))

    stop_conditions = data.get("stop_conditions")
    if not isinstance(stop_conditions, list) or not stop_conditions:
        errors.append("stop_conditions must be a non-empty list")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        errors.append("files must be a non-empty list")
        file_checks: list[dict[str, Any]] = []
    else:
        file_checks = [validate_file_entry(entry, index) for index, entry in enumerate(files)]
        for check in file_checks:
            for error in check.get("errors", []):
                errors.append(f"{check.get('path')}: {error}")
            for warning in check.get("warnings", []):
                warnings.append(f"{check.get('path')}: {warning}")
        included_count = sum(1 for item in files if isinstance(item, dict) and item.get("included") is True)
        if data.get("included_file_count") != included_count:
            errors.append("included_file_count does not match files")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "profile": data.get("profile"),
        "file_count": len(files) if isinstance(files, list) else 0,
        "file_checks": file_checks,
    }


def validate_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "kind": None,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "profile": None,
        }

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("kind") != EVIDENCE_KIND:
        errors.append(f"kind must be {EVIDENCE_KIND}")
    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if data.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append(f"apply_mode must be {EXPECTED_APPLY_MODE}")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("passed") is not True:
        errors.append("evidence passed must be true")
    if data.get("forbidden_path_count") != 0:
        errors.append("forbidden_path_count must be 0")
    if data.get("required_missing") not in ([], None):
        errors.append("required_missing must be empty")
    decision = data.get("decision")
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
    else:
        if decision.get("context_pack_built") is not True:
            errors.append("decision.context_pack_built must be true")
        if decision.get("provider_execution_seen") is not False:
            errors.append("decision.provider_execution_seen must be false")
        if decision.get("source_writes_performed") is not False:
            errors.append("decision.source_writes_performed must be false")

    included_paths = data.get("included_paths")
    if not isinstance(included_paths, list) or not included_paths:
        errors.append("included_paths must be a non-empty list")
    elif isinstance(data.get("included_file_count"), int) and data["included_file_count"] != sum(
        1 for item in included_paths if isinstance(item, dict) and item.get("included") is True
    ):
        errors.append("included_file_count does not match included_paths")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "profile": data.get("profile"),
    }


def validate_ai_context_packs(repo_root: Path, pack_paths: list[Path], evidence_paths: list[Path]) -> dict[str, Any]:
    pack_checks = [validate_pack(path, repo_root) for path in pack_paths]
    evidence_checks = [validate_evidence(path, repo_root) for path in evidence_paths]
    errors = [
        f"{item['path']}: {error}"
        for item in [*pack_checks, *evidence_checks]
        for error in item.get("errors", [])
    ]
    warnings = [
        f"{item['path']}: {warning}"
        for item in [*pack_checks, *evidence_checks]
        for warning in item.get("warnings", [])
    ]
    if not pack_checks and not evidence_checks:
        errors.append("no AI context pack or evidence paths were provided")

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "pack_count": len(pack_checks),
        "evidence_count": len(evidence_checks),
        "pack_checks": pack_checks,
        "evidence_checks": evidence_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--pack", action="append", default=[], help="Context pack JSON path. Repeatable or comma-separated.")
    parser.add_argument("--evidence", action="append", default=[], help="Context pack evidence JSON path. Repeatable or comma-separated.")
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    pack_paths = [
        resolve_repo_path(repo_root, raw)
        for raw in split_path_values(list(args.pack or []))
    ]
    evidence_paths = [
        resolve_repo_path(repo_root, raw)
        for raw in split_path_values(list(args.evidence or []))
    ]
    if not pack_paths and not evidence_paths:
        pack_paths = [repo_root / "output" / "ai_context_packs" / "project_self_improvement.json"]
        evidence_paths = [repo_root / "docs" / "LOCAL_VALIDATION_EVIDENCE" / "project_self_improvement_context_pack_evidence.json"]

    report = validate_ai_context_packs(repo_root, pack_paths, evidence_paths)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
