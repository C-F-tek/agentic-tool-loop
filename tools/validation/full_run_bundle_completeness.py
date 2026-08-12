from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

EXPECTED_KIND = "full_run_evidence_bundle_completeness"


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def split_values(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            item = part.strip().strip("'\"").replace("\\", "/").lstrip("./")
            if item and item not in out:
                out.append(item)
    return out


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def read_zip_members(path: Path) -> tuple[set[str], str | None]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            return {name.replace("\\", "/") for name in archive.namelist()}, None
    except OSError as exc:
        return set(), f"{type(exc).__name__}: {exc}"
    except zipfile.BadZipFile as exc:
        return set(), f"BadZipFile: {exc}"


def validate_report_shape(report: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if report.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND!r}")
    if report.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if "artifacts" not in report or not isinstance(report.get("artifacts"), list):
        errors.append("artifacts must be a list")
    if "zip_path" not in report:
        errors.append("zip_path is required")
    if report.get("errors"):
        errors.extend(f"builder error: {item}" for item in report.get("errors") or [])
    if report.get("passed") is False:
        errors.append("builder report passed=false")
    if not isinstance(report.get("included_artifact_count"), int):
        warnings.append("included_artifact_count should be an integer")
    if not isinstance(report.get("zip_member_count"), int):
        warnings.append("zip_member_count should be an integer")
    return errors, warnings


def validate_artifacts_against_zip(report: dict[str, Any], members: set[str]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), list) else []
    for index, raw in enumerate(artifacts):
        if not isinstance(raw, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        rel = str(raw.get("path") or "").replace("\\", "/").lstrip("./")
        required = bool(raw.get("required"))
        included = bool(raw.get("included_in_zip"))
        is_dir = bool(raw.get("is_dir"))
        member_count = int(raw.get("zip_member_count") or 0)
        ok = True
        detail_errors: list[str] = []
        if not rel:
            ok = False
            detail_errors.append("missing path")
        elif included and not is_dir and rel not in members:
            ok = False
            detail_errors.append("included file is missing from ZIP")
        elif included and is_dir:
            matching = [name for name in members if name.startswith(rel.rstrip("/") + "/")]
            if not matching:
                ok = False
                detail_errors.append("included directory has no ZIP members")
            elif member_count and len(matching) != member_count:
                warnings.append(f"{rel}: reported {member_count} members, ZIP has {len(matching)}")
        elif required and not included:
            ok = False
            detail_errors.append("required artifact not included")
        if detail_errors:
            errors.extend(f"{rel or f'artifacts[{index}]'}: {item}" for item in detail_errors)
        checks.append(
            {
                "index": index,
                "path": rel,
                "required": required,
                "included_in_zip": included,
                "is_dir": is_dir,
                "zip_member_count": member_count,
                "ok": ok,
                "errors": detail_errors,
            }
        )
    return errors, warnings, checks


def validate_required_recursive_roots(required_roots: list[str], members: set[str]) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for root in required_roots:
        normalized = root.replace("\\", "/").rstrip("/")
        matching = [name for name in members if name.startswith(normalized + "/")]
        ok = bool(matching)
        if not ok:
            errors.append(f"required recursive root missing from ZIP: {normalized}")
        checks.append({"root": normalized, "zip_member_count": len(matching), "ok": ok})
    return errors, checks


def validate_bundle(repo_root: Path, zip_path: Path, report_path: Path | None, required_recursive_roots: list[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    members, zip_error = read_zip_members(zip_path)
    if zip_error:
        errors.append(f"{repo_relative(zip_path, repo_root)}: {zip_error}")

    report: dict[str, Any] | None = None
    artifact_checks: list[dict[str, Any]] = []
    if report_path:
        report, report_error = read_json_object(report_path)
        if report_error or report is None:
            errors.append(f"{repo_relative(report_path, repo_root)}: {report_error}")
        else:
            shape_errors, shape_warnings = validate_report_shape(report)
            errors.extend(shape_errors)
            warnings.extend(shape_warnings)
            artifact_errors, artifact_warnings, artifact_checks = validate_artifacts_against_zip(report, members)
            errors.extend(artifact_errors)
            warnings.extend(artifact_warnings)
    else:
        warnings.append("no completeness report provided; ZIP-only validation is limited")

    effective_required_roots = list(required_recursive_roots)
    if report and isinstance(report.get("required_recursive_roots"), list):
        for item in report["required_recursive_roots"]:
            normalized = str(item).replace("\\", "/").rstrip("/")
            if normalized and normalized not in effective_required_roots:
                effective_required_roots.append(normalized)

    root_errors, root_checks = validate_required_recursive_roots(effective_required_roots, members)
    errors.extend(root_errors)

    return {
        "schema_version": 1,
        "kind": "full_run_bundle_completeness_validation",
        "repo_root": str(repo_root),
        "bundle": repo_relative(zip_path, repo_root),
        "completeness_report": repo_relative(report_path, repo_root) if report_path else None,
        "passed": not errors,
        "zip_member_count": len(members),
        "artifact_checks": artifact_checks,
        "required_recursive_root_checks": root_checks,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
    }
