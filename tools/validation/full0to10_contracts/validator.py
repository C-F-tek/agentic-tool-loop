"""Full0To10 contract report builder."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .hardware_contract import check_hardware_contract
from .io_utils import read_json, utc_now
from .memory_contract import check_memory_contract
from .paths import collect_bundle_paths, collect_evidence_paths
from .roles import check_required_roles


def build_report(
    repo_root: Path,
    bundle_path: Path | None,
    evidence_dir: Path | None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    bundle: dict[str, Any] = {}
    bundle_error = None
    if bundle_path:
        bundle, bundle_error = read_json(bundle_path)
        bundle = bundle or {}

    bundle_paths = collect_bundle_paths(bundle)
    evidence_paths = collect_evidence_paths(repo_root, evidence_dir)
    all_paths = sorted(set(bundle_paths + evidence_paths))
    role_checks = check_required_roles(all_paths)
    memory_contract = check_memory_contract(bundle, all_paths)
    hardware_contract = check_hardware_contract(bundle, all_paths)

    errors: list[str] = []
    warnings: list[str] = []
    if bundle_error:
        errors.append(f"bundle_json_error: {bundle_error}")
    for role in role_checks:
        if not role.passed:
            errors.append(f"missing_required_bundle_role: {role.role}")
    errors.extend(memory_contract["errors"])
    errors.extend(hardware_contract["errors"])
    warnings.extend(memory_contract["warnings"])
    warnings.extend(hardware_contract["warnings"])

    return {
        "kind": "full0to10_bundle_contract_validation",
        "generated_at": utc_now(),
        "passed": not errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "inputs": {
            "repo_root": repo_root.as_posix(),
            "bundle": bundle_path.as_posix() if bundle_path else None,
            "evidence_dir": evidence_dir.as_posix() if evidence_dir else None,
        },
        "path_count": len(all_paths),
        "required_roles": [role.to_json() for role in role_checks],
        "memory_contract": memory_contract,
        "hardware_contract": hardware_contract,
        "errors": errors,
        "warnings": warnings,
    }
