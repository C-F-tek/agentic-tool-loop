"""Full0To10 run manifest assembly."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .classify import classify_records, summarize_roles
from .constants import DEFAULT_SCAN_ROOTS
from .hardware import build_hardware_manifest
from .memory import build_memory_manifest
from .scan import scan_roots as scan_manifest_roots


def build_manifest(
    repo_root: Path,
    scan_roots_arg: list[str] | None = None,
    workers: int = 6,
) -> dict[str, Any]:
    scan_root_names = scan_roots_arg or list(DEFAULT_SCAN_ROOTS)
    roots = [Path(item) for item in scan_root_names]
    records = scan_manifest_roots(repo_root, roots, workers=workers)
    roles = classify_records(records)
    role_summary = summarize_roles(roles)
    memory = build_memory_manifest(repo_root)
    hardware = build_hardware_manifest()

    errors: list[str] = []
    warnings: list[str] = []
    if not role_summary["passed"]:
        errors.extend(f"missing_role: {role}" for role in role_summary["missing_roles"])

    return {
        "kind": "full0to10_run_manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "scan_roots": scan_root_names,
        "artifact_count": len(records),
        "artifacts": records,
        "role_summary": role_summary,
        "memory": memory,
        "hardware": hardware,
        "errors": errors,
        "warnings": warnings,
    }
