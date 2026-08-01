"""Diagnostic conflict detection forfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 planner memory records.

The detector is read-only: it does not delete SQLite rows, rewrite memory
surfaces or decide planner actions. It marks records that appear stale or
contradictory so consumers can inspect them explicitly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


SCHEMA = "memory_conflict_report.v1"
logger = logging.getLogger(__name__)


def _records_from(surface_or_records: Any) -> list[dict[str, Any]]:
    if isinstance(surface_or_records, dict):
        raw = surface_or_records.get("records")
    else:
        raw = surface_or_records
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    data = record.get("metadata")
    return data if isinstance(data, dict) else {}


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("id") or record.get("created_at") or "")


def _split_paths(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip().replace("\\", "/") for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip().replace("\\", "/") for item in text.replace(";", ",").split(",") if item.strip()]


def _referenced_paths(record: dict[str, Any]) -> list[str]:
    meta = _metadata(record)
    paths: list[str] = []
    for source in (record, meta):
        for key in (
            "path",
            "paths",
            "referenced_path",
            "referenced_paths",
            "resolved_goal_file",
            "target_file",
            "target_path",
        ):
            paths.extend(_split_paths(source.get(key)))
    return list(dict.fromkeys(path for path in paths if path))


def _branch(record: dict[str, Any]) -> str:
    meta = _metadata(record)
    return str(record.get("branch") or meta.get("branch") or meta.get("git_branch") or "").strip()


def _path_hashes(record: dict[str, Any]) -> dict[str, str]:
    meta = _metadata(record)
    raw = record.get("file_hashes") or meta.get("file_hashes") or meta.get("path_hashes") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(path).strip().replace("\\", "/"): str(value).strip()
        for path, value in raw.items()
        if str(path).strip() and str(value).strip()
    }


def _is_under_repo(root: Path, rel: str) -> bool:
    try:
        candidate = (root / rel).resolve(strict=False)
        candidate.relative_to(root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _path_status(root: Path, rel: str) -> dict[str, Any]:
    details: dict[str, Any] = {"path": rel}
    if not _is_under_repo(root, rel):
        return {**details, "path_status": "outside_repo"}
    try:
        candidate = (root / rel).resolve(strict=False)
        details["resolved_path"] = str(candidate)
        if not candidate.exists():
            return {**details, "path_status": "missing"}
        if not candidate.is_file() and not candidate.is_dir():
            return {**details, "path_status": "not_regular_path"}
        return {**details, "path_status": "exists"}
    except PermissionError as exc:
        logger.debug("Memory conflict path permission denied. path=%s", rel)
        return {
            **details,
            "path_status": "permission_denied",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    except OSError as exc:
        return {
            **details,
            "path_status": "filesystem_error",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def _ignore(record: dict[str, Any], *, reason: str, severity: str = "medium", details: dict[str, Any] | None = None) -> dict[str, Any]:
    detail_payload = details or {}
    path_status = str(detail_payload.get("path_status") or "")
    error_type = str(detail_payload.get("error_type") or "")
    return {
        "record_id": _record_id(record),
        "reason": reason,
        "severity": severity,
        "details": detail_payload,
        "path_status": path_status or None,
        "error_type": error_type or None,
        "is_false_positive": path_status in {"missing", "permission_denied"},
        "diagnostic_only": True,
    }


def detect_memory_conflicts(
    surface_or_records: Any,
    *,
    repo_root: str | Path | None = None,
    current_branch: str = "",
    current_file_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return usable/ignored memory records plus conflict diagnostics."""

    records = _records_from(surface_or_records)
    root = Path(repo_root).resolve(strict=False) if repo_root else None
    branch = str(current_branch or "").strip()
    file_hashes = {
        str(path).strip().replace("\\", "/"): str(value).strip()
        for path, value in (current_file_hashes or {}).items()
        if str(path).strip() and str(value).strip()
    }
    usable: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for record in records:
        record_branch = _branch(record)
        if branch and record_branch and record_branch != branch:
            ignored.append(_ignore(record, reason="wrong_branch_record", details={"record_branch": record_branch, "current_branch": branch}))
            continue

        missing_path = ""
        out_of_repo_path = ""
        path_details: dict[str, Any] = {}
        if root is not None:
            for rel in _referenced_paths(record):
                status = _path_status(root, rel)
                if status.get("path_status") == "outside_repo":
                    out_of_repo_path = rel
                    path_details = status
                    break
                if status.get("path_status") in {"missing", "permission_denied", "filesystem_error"}:
                    missing_path = rel
                    path_details = status
                    break
        if out_of_repo_path:
            ignored.append(_ignore(record, reason="referenced_path_outside_repo", severity="high", details=path_details or {"path": out_of_repo_path}))
            continue
        if missing_path:
            reason = (
                "referenced_path_permission_denied"
                if path_details.get("path_status") == "permission_denied"
                else "referenced_path_filesystem_error"
                if path_details.get("path_status") == "filesystem_error"
                else "referenced_path_no_longer_exists"
            )
            ignored.append(_ignore(record, reason=reason, details=path_details or {"path": missing_path}))
            continue

        hash_mismatch = ""
        for rel, remembered_hash in _path_hashes(record).items():
            current_hash = file_hashes.get(rel)
            if current_hash and current_hash != remembered_hash:
                hash_mismatch = rel
                conflicts.append(
                    {
                        "record_id": _record_id(record),
                        "reason": "referenced_file_hash_mismatch",
                        "path": rel,
                        "remembered_hash": remembered_hash,
                        "current_hash": current_hash,
                        "current_hash_source": "current_file_hashes",
                        "severity": "medium",
                        "diagnostic_only": True,
                    }
                )
                break
        if hash_mismatch:
            ignored.append(_ignore(
                record,
                reason="referenced_file_hash_mismatch",
                details={"path": hash_mismatch, "path_status": "hash_mismatch"},
            ))
            continue

        usable.append(record)

    return {
        "schema": SCHEMA,
        "usable_memory_records": usable,
        "ignored_memory_records": ignored,
        "memory_conflicts": conflicts,
        "input_record_count": len(records),
        "usable_count": len(usable),
        "ignored_count": len(ignored),
        "diagnostic_only": True,
        "does_not_mutate_memory": True,
    }
