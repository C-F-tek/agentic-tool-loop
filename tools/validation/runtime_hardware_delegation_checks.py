from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_HARDWARE_KIND = "runtime_hardware_capability_manifest"
SAFE_SIDE_EFFECTS = {"read_only", "report_only"}
REQUIRED_RESOURCES = ("CPU", "GPU.0", "NPU")


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
            item = part.strip().strip("'\"")
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


def validate_boolean_false(data: dict[str, Any], field: str, errors: list[str], label: str) -> None:
    if data.get(field) is not False:
        errors.append(f"{label}: {field} must be false")


def validate_capability_entry(entry: Any, index: int) -> dict[str, Any]:
    label = f"capabilities[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(entry, dict):
        return {"index": index, "resource": None, "ok": False, "errors": [f"{label} must be an object"], "warnings": warnings}

    resource = str(entry.get("resource") or "")
    name = str(entry.get("name") or "")
    allowed = entry.get("allowed_side_effects")
    if not resource:
        errors.append("resource is required")
    if not name:
        errors.append("name is required")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed_side_effects must be a non-empty list")
    else:
        unsafe = [item for item in allowed if str(item) not in SAFE_SIDE_EFFECTS]
        if unsafe:
            errors.append(f"unsafe side effects for report-only stage: {unsafe}")

    for field in (
        "source_writes_allowed",
        "patch_application_allowed",
        "persistent_memory_write_allowed",
        "media_runtime_allowed",
        "network_or_secret_access_allowed",
    ):
        if entry.get(field) is not False:
            errors.append(f"{field} must be false")

    status = entry.get("status")
    if status not in {"available", "unavailable", "degraded", "blocked", "unknown"}:
        warnings.append(f"unexpected status: {status!r}")

    return {
        "index": index,
        "resource": resource,
        "name": name,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_hardware_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    data, parse_error = read_json_object(path)
    errors: list[str] = []
    warnings: list[str] = []
    if parse_error or data is None:
        return {
            "path": repo_relative(path, repo_root),
            "ok": False,
            "kind": None,
            "capability_checks": [],
            "errors": [parse_error or "unable to read hardware manifest"],
            "warnings": warnings,
        }

    if data.get("kind") != EXPECTED_HARDWARE_KIND:
        errors.append(f"kind must be {EXPECTED_HARDWARE_KIND!r}")
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    validate_boolean_false(data, "provider_execution_performed", errors, "hardware manifest")
    validate_boolean_false(data, "patch_application_performed", errors, "hardware manifest")
    validate_boolean_false(data, "source_writes_performed", errors, "hardware manifest")
    validate_boolean_false(data, "persistent_memory_write_performed", errors, "hardware manifest")

    raw_capabilities = data.get("capabilities")
    if not isinstance(raw_capabilities, list):
        errors.append("capabilities must be a list")
        capability_checks: list[dict[str, Any]] = []
    else:
        capability_checks = [validate_capability_entry(item, index) for index, item in enumerate(raw_capabilities)]
        for check in capability_checks:
            errors.extend(f"{check.get('name') or check.get('index')}: {error}" for error in check.get("errors", []))
            warnings.extend(f"{check.get('name') or check.get('index')}: {warning}" for warning in check.get("warnings", []))

    visible_resources = {str(item.get("resource")) for item in raw_capabilities if isinstance(item, dict)} if isinstance(raw_capabilities, list) else set()
    for resource in REQUIRED_RESOURCES:
        if resource not in visible_resources:
            errors.append(f"required resource not visible in manifest: {resource}")

    return {
        "path": repo_relative(path, repo_root),
        "ok": not errors,
        "kind": data.get("kind"),
        "capability_checks": capability_checks,
        "errors": errors,
        "warnings": warnings,
    }


def validate_delegated_report(path: Path, repo_root: Path) -> dict[str, Any]:
    data, parse_error = read_json_object(path)
    errors: list[str] = []
    warnings: list[str] = []
    if parse_error or data is None:
        return {
            "path": repo_relative(path, repo_root),
            "ok": False,
            "errors": [parse_error or "unable to read delegated report"],
            "warnings": warnings,
        }

    side_effect = str(data.get("side_effect_class") or "report_only")
    if side_effect not in SAFE_SIDE_EFFECTS:
        errors.append(f"unsafe side_effect_class for report-only stage: {side_effect}")
    for field in (
        "source_writes_performed",
        "patch_application_performed",
        "persistent_memory_write_performed",
    ):
        if data.get(field) is not False:
            errors.append(f"{field} must be false")
    if "timeout_seconds" not in data:
        warnings.append("timeout_seconds is not recorded")
    if "target_resource" not in data:
        warnings.append("target_resource is not recorded")

    return {
        "path": repo_relative(path, repo_root),
        "ok": not errors,
        "kind": data.get("kind"),
        "target_resource": data.get("target_resource"),
        "errors": errors,
        "warnings": warnings,
    }


def validate_contract(repo_root: Path, hardware_manifest: Path, delegated_reports: list[Path]) -> dict[str, Any]:
    hardware = validate_hardware_manifest(hardware_manifest, repo_root)
    delegated = [validate_delegated_report(path, repo_root) for path in delegated_reports]
    errors = list(hardware.get("errors") or [])
    warnings = list(hardware.get("warnings") or [])
    for item in delegated:
        errors.extend(f"{item['path']}: {error}" for error in item.get("errors", []))
        warnings.extend(f"{item['path']}: {warning}" for warning in item.get("warnings", []))
    return {
        "schema_version": 1,
        "kind": "runtime_hardware_delegation_contract_validation",
        "repo_root": str(repo_root),
        "passed": not errors,
        "hardware_manifest": hardware,
        "delegated_report_checks": delegated,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
    }
