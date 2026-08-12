"""SQLite memory visibility contract checks."""
from __future__ import annotations

import json
from typing import Any

from .constants import DB_SUFFIXES, EXPECTED_MEMORY_PATHS
from .io_utils import iter_values, normalize_path_like


def field_values(bundle: dict[str, Any], field_name: str) -> list[Any]:
    values: list[Any] = []
    if field_name in bundle:
        values.append(bundle[field_name])
    for value in iter_values(bundle):
        if isinstance(value, dict) and field_name in value:
            values.append(value[field_name])
    return values


def find_db_content_violations(bundle: dict[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for value in iter_values(bundle):
        if not isinstance(value, dict):
            continue
        path = normalize_path_like(str(value.get("path", "")))
        if not path.lower().endswith(DB_SUFFIXES):
            continue
        if value.get("content_included") or value.get("content") or value.get("preview"):
            violations.append({"path": path, "reason": "database_artifact_content_included"})
    return violations


def check_memory_contract(bundle: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    text = json.dumps(bundle, sort_keys=True, ensure_ascii=False) + "\n" + "\n".join(paths)
    declared_paths = [path for path in EXPECTED_MEMORY_PATHS if path in text]
    persistent_values = field_values(bundle, "persistent_memory_write_performed")
    sqlite_values = field_values(bundle, "sqlite_write_performed")
    db_content_violations = find_db_content_violations(bundle)

    scratch_declared = EXPECTED_MEMORY_PATHS[0] in declared_paths or "operational_context.sqlite" in text
    persistent_declared = EXPECTED_MEMORY_PATHS[1] in declared_paths or "agent_memory.sqlite" in text
    sqlite_visibility_seen = bool(persistent_values or sqlite_values or "runtime_sqlite_memory" in text)
    persistent_write_blocked = not any(value is True for value in persistent_values)

    errors: list[str] = []
    warnings: list[str] = []
    if not scratch_declared:
        errors.append("operational SQLite scratch memory path is not visible")
    if not persistent_declared:
        errors.append("persistent SQLite memory path is not visible")
    if not sqlite_visibility_seen:
        warnings.append("SQLite read/write visibility flags are not present")
    if not persistent_write_blocked:
        errors.append("persistent memory write appears enabled; Full0To10 default must keep it guarded")
    if db_content_violations:
        errors.append("SQLite/DB artifact content is included in bundle")

    return {
        "passed": not errors,
        "scratch_memory_declared": scratch_declared,
        "persistent_memory_declared": persistent_declared,
        "sqlite_visibility_seen": sqlite_visibility_seen,
        "persistent_memory_write_blocked": persistent_write_blocked,
        "db_content_violations": db_content_violations,
        "errors": errors,
        "warnings": warnings,
    }
