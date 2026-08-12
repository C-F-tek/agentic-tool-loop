"""Readiness scoring for Full0To10 quality gate."""
from __future__ import annotations

from typing import Any


def score_quality(checks: dict[str, Any], split_advisory: dict[str, Any]) -> dict[str, Any]:
    score = 100
    blockers = []
    warnings = []

    if not checks["required_scripts"]["passed"]:
        score -= 35
        blockers.append("missing_required_scripts")
    if not checks["md_split_quarantine"]["passed"]:
        score -= 25
        blockers.append("source_side_md_split_dirs_present")
    if not checks["report_visibility"]["passed"]:
        score -= 15
        warnings.append("some_recent_quality_reports_not_visible")

    if split_advisory["spec_count"] == 0:
        warnings.append("no_refactor_patch_specs_supplied")
    if split_advisory["hardware_contract_suggestions"]:
        warnings.append("hardware_contract_suggestions_pending")

    score = max(0, score)
    return {
        "score": score,
        "ready_for_real_run": score >= 85 and not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }
