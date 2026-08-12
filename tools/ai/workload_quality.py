#!/usr/bin/env python3
"""Helpers for AI workload quality-based advisory routing.

The helpers in this module are intentionally report-only. They inspect an
already-generated ``ai_workload_report_quality`` JSON report and derive which
workload lanes may be used as advisory context by packet/proposal builders.

They do not execute providers, do not call Ollama/OpenVINO/NPU/GPU and do not
modify legacy runtime outputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_QUALITY_REPORT = "output/validation/ai_workload_report_quality.json"
TRACKED_WORKLOAD_PATH_SUFFIXES = (
    "output/ai_packets/npu_real_workload_report.md",
    "output/ai_packets/ollama_gpu_real_workload_report.md",
)
WORKLOAD_LANE_BY_SUFFIX = {
    "output/ai_packets/npu_real_workload_report.md": "npu",
    "output/ai_packets/ollama_gpu_real_workload_report.md": "ollama",
}


@dataclass(frozen=True)
class AdvisoryContextDecision:
    """Decision for one advisory context file."""

    path: str
    lane: str
    trusted: bool
    reason: str
    classification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "lane": self.lane,
            "trusted": self.trusted,
            "reason": self.reason,
            "classification": self.classification,
        }


def _normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def _resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def tracked_workload_lane_for_path(path: str | Path) -> str:
    normalized = _normalize_path(path)
    for suffix, lane in WORKLOAD_LANE_BY_SUFFIX.items():
        if normalized.endswith(suffix):
            return lane
    return ""


def is_tracked_workload_path(path: str | Path) -> bool:
    return bool(tracked_workload_lane_for_path(path))


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - caller turns missing/unreadable into disabled routing.
        return None
    return data if isinstance(data, dict) else None


def load_workload_quality_report(repo_root: Path, report_path: str | Path = DEFAULT_QUALITY_REPORT) -> dict[str, Any] | None:
    """Load the workload quality report, returning ``None`` when unavailable."""

    return read_json_if_exists(_resolve_repo_path(repo_root, report_path))


def is_quality_report(data: dict[str, Any] | None) -> bool:
    return isinstance(data, dict) and data.get("kind") == "ai_workload_report_quality"


def _dedupe_strings(items: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item)
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def usable_lanes(report: dict[str, Any] | None) -> list[str]:
    if not is_quality_report(report):
        return []
    return _dedupe_strings(report.get("usable_lanes") or [])


def unusable_lanes(report: dict[str, Any] | None) -> list[str]:
    if not is_quality_report(report):
        return []
    return _dedupe_strings(report.get("unusable_lanes") or [])


def result_items(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not is_quality_report(report):
        return []
    checks = report.get("checks") or {}
    results = checks.get("results") if isinstance(checks, dict) else []
    return [item for item in results if isinstance(item, dict)]


def results_by_path(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in result_items(report):
        path = item.get("path")
        if path:
            out[_normalize_path(str(path))] = item
    return out


def results_by_lane(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in result_items(report):
        lane = item.get("lane")
        if lane:
            out[str(lane)] = item
    return out


def lane_for_context_path(path: str | Path, report: dict[str, Any] | None) -> str:
    normalized = _normalize_path(path)
    by_path = results_by_path(report)
    if normalized in by_path:
        return str(by_path[normalized].get("lane") or "")
    # Accept matching by suffix so absolute local paths and repo-relative paths
    # resolve to the same workload report entry.
    for known_path, item in by_path.items():
        if normalized.endswith(known_path) or known_path.endswith(normalized):
            return str(item.get("lane") or "")
    return tracked_workload_lane_for_path(normalized)


def classify_context_path(path: str | Path, report: dict[str, Any] | None) -> AdvisoryContextDecision:
    """Classify one context file against the quality report.

    Unknown paths remain trusted because the gate only applies to known generated
    workload reports. Known workload report paths fail closed when the quality
    report is missing or unreadable.
    """

    normalized = _normalize_path(path)
    lane = lane_for_context_path(normalized, report)
    if not lane:
        return AdvisoryContextDecision(path=normalized, lane="", trusted=True, reason="not_a_tracked_workload_report")

    if not is_quality_report(report):
        return AdvisoryContextDecision(
            path=normalized,
            lane=lane,
            trusted=False,
            reason="quality_report_missing_fail_closed",
            classification="quality_unknown",
        )

    by_lane = results_by_lane(report)
    item = by_lane.get(lane, {})
    classification = str(item.get("classification") or "")
    advisory_use = item.get("advisory_use") if isinstance(item.get("advisory_use"), dict) else {}
    if lane in usable_lanes(report) and item.get("usable") is True and advisory_use.get("allowed_as_advisory_context") is not False:
        return AdvisoryContextDecision(
            path=normalized,
            lane=lane,
            trusted=True,
            reason="usable_text",
            classification=classification,
        )
    return AdvisoryContextDecision(
        path=normalized,
        lane=lane,
        trusted=False,
        reason=classification or advisory_use.get("reason") or "unusable_workload_report",
        classification=classification,
    )


def route_context_files_by_quality(context_files: Iterable[str], report: dict[str, Any] | None) -> dict[str, Any]:
    """Return trusted/excluded context-file routing for workload reports."""

    decisions = [classify_context_path(path, report) for path in context_files]
    trusted = [item.to_dict() for item in decisions if item.trusted]
    excluded = [item.to_dict() for item in decisions if not item.trusted]
    return {
        "quality_report_present": is_quality_report(report),
        "advisory_lanes": usable_lanes(report),
        "excluded_advisory_lanes": unusable_lanes(report),
        "trusted_context_files": trusted,
        "excluded_context_files": excluded,
        "decisions": [item.to_dict() for item in decisions],
    }


def trusted_context_file_paths(context_files: Iterable[str], report: dict[str, Any] | None) -> list[str]:
    return [item["path"] for item in route_context_files_by_quality(context_files, report)["trusted_context_files"]]


def build_quality_routing_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    """Compact report-level routing summary for packets/proposals."""

    if not is_quality_report(report):
        return {
            "quality_report_present": False,
            "advisory_lanes": [],
            "excluded_advisory_lanes": [],
            "provider_execution_performed": False,
            "policy": "quality_routing_fail_closed_for_tracked_workload_reports",
        }
    return {
        "quality_report_present": True,
        "advisory_lanes": usable_lanes(report),
        "excluded_advisory_lanes": unusable_lanes(report),
        "provider_execution_performed": False,
        "policy": "usable_text_lanes_only_for_advisory_context",
    }
