"""Quality checks for Full0To10 readiness."""
from __future__ import annotations

from typing import Any

from .constants import REPORT_PATTERNS


def check_required_scripts(records: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [item["path"] for item in records if not item["exists"]]
    return {"passed": not missing, "missing": missing, "records": records}


def check_md_split_quarantine(source_side_dirs: list[str]) -> dict[str, Any]:
    return {
        "passed": not source_side_dirs,
        "source_side_md_split_count": len(source_side_dirs),
        "source_side_md_split_dirs": source_side_dirs[:100],
    }


def check_report_visibility(reports: list[str]) -> dict[str, Any]:
    found: dict[str, list[str]] = {}
    for role, pattern in REPORT_PATTERNS.items():
        found[role] = [path for path in reports if pattern in path]
    missing = [role for role, paths in found.items() if not paths]
    return {
        "passed": not missing,
        "missing_report_roles": missing,
        "found_report_counts": {role: len(paths) for role, paths in found.items()},
        "found_reports": {role: paths[:20] for role, paths in found.items()},
    }


def build_quality_checks(records: list[dict[str, Any]], source_side_dirs: list[str], reports: list[str]) -> dict[str, Any]:
    return {
        "required_scripts": check_required_scripts(records),
        "md_split_quarantine": check_md_split_quarantine(source_side_dirs),
        "report_visibility": check_report_visibility(reports),
    }
