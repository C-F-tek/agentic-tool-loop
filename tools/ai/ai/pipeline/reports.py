"""Report helpers for reusable AI artifact pipelines."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import PipelineLane, PipelineReport, PipelineResult


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def write_json_report(path: str | Path, payload: PipelineReport | dict) -> Path:
    """Write a JSON report and return the resolved output path."""
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    data = payload.to_dict() if isinstance(payload, PipelineReport) else payload
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def results_to_dicts(results: Iterable[PipelineResult]) -> list[dict]:
    """Serialize pipeline results to dictionaries."""
    return [result.to_dict() for result in results]


def results_by_lane(results: Iterable[PipelineResult]) -> dict[str, list[str]]:
    """Return result step names grouped by lane."""
    grouped: dict[str, list[str]] = {}
    for result in results:
        grouped.setdefault(result.step.lane.value, []).append(result.step.name)
    return grouped


def failed_results(results: Iterable[PipelineResult]) -> list[PipelineResult]:
    """Return failed results, excluding steps explicitly allowed to fail."""
    return [result for result in results if not result.ok]


def build_report(
    *,
    schema_version: int,
    repo_root: str | Path,
    output_dir: str | Path,
    dry_run: bool,
    preflight: dict,
    results: Iterable[PipelineResult],
    metadata: dict | None = None,
) -> PipelineReport:
    """Build a standard pipeline report from results."""
    result_tuple = tuple(results)
    return PipelineReport(
        schema_version=schema_version,
        generated_at=utc_now_iso(),
        repo_root=Path(repo_root).expanduser().resolve(),
        output_dir=Path(output_dir).expanduser().resolve(),
        dry_run=dry_run,
        passed=bool(preflight.get("passed", True)) and not failed_results(result_tuple),
        preflight=preflight,
        results=result_tuple,
        metadata=dict(metadata or {}),
    )


def lane_summary(results: Iterable[PipelineResult]) -> dict[str, int]:
    """Return count of executed steps per lane."""
    summary = {lane.value: 0 for lane in PipelineLane}
    for result in results:
        summary[result.step.lane.value] = summary.get(result.step.lane.value, 0) + 1
    return {lane: count for lane, count in summary.items() if count}
