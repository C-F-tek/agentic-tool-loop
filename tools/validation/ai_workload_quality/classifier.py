"""Classifier for AI workload report quality."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .metrics import text_metrics
from .paths import relative_or_absolute_path
from .roles import advisory_use, lane_role


def classify_report(path: Path, lane: str, repo_root: Path) -> dict[str, Any]:
    role = lane_role(lane)
    rel_path = relative_or_absolute_path(path, repo_root)
    if not path.exists():
        return {
            "path": rel_path,
            "lane": lane,
            "provider": role["provider"],
            "compute_lane": role["compute_lane"],
            "exists": False,
            "usable": False,
            "classification": "missing_explicit_report",
            "advisory_use": advisory_use(lane, False),
            "provider_execution_performed": False,
            "errors": ["explicitly selected report file is missing"],
            "warnings": [],
            "metrics": {},
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    metrics = text_metrics(text)
    errors: list[str] = []
    warnings: list[str] = []

    if metrics["chars"] < 120:
        errors.append("report is too short to be useful")
    if metrics["alpha_ratio"] < 0.18:
        errors.append("alphabetic character ratio is too low")
    if metrics["word_count"] < 20:
        errors.append("word count is too low")
    if metrics["hexish_ratio"] > 0.82 and metrics["alpha_ratio"] < 0.28:
        errors.append("report appears numeric/hex-like rather than natural language")
    if metrics["printable_ratio"] < 0.95:
        errors.append("report contains too many non-printable characters")
    if metrics["markdown_heading_count"] == 0 and metrics["sentence_marker_count"] < 3:
        warnings.append("report lacks Markdown headings and has few sentence markers")

    usable = not errors
    return {
        "path": rel_path,
        "lane": lane,
        "provider": role["provider"],
        "compute_lane": role["compute_lane"],
        "exists": True,
        "usable": usable,
        "classification": "usable_text" if usable else "unusable_output",
        "advisory_use": advisory_use(lane, usable),
        "provider_execution_performed": False,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }
