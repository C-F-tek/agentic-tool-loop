"""Markdown report helpers for AI artifact pipeline dry-run outputs."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def bool_icon(value: Any) -> str:
    """Return a compact Markdown-friendly status icon."""
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "N/A"


def table_cell(value: Any) -> str:
    """Return a safe one-line Markdown table cell."""
    if value is None:
        return ""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def lane_counts(lanes: Any) -> dict[str, int]:
    """Return counts by lane from a matrix case lane payload."""
    if not isinstance(lanes, dict):
        return {}
    return {str(lane): len(steps) if isinstance(steps, list) else 0 for lane, steps in lanes.items()}


def case_status(result: dict[str, Any]) -> str:
    """Return a human-readable status for one matrix case."""
    return bool_icon(result.get("returncode") == 0 and result.get("report_passed") is True)


def render_dry_run_matrix_markdown(report: dict[str, Any]) -> str:
    """Render a dry-run matrix JSON report as readable Markdown."""
    results = report.get("results") if isinstance(report.get("results"), list) else []
    lines: list[str] = []
    lines.append("# AI Pipeline Dry-run Matrix Report\n")
    lines.append("## Summary\n")
    lines.append(f"- Passed: `{bool_icon(report.get('passed'))}`\n")
    lines.append(f"- Cases executed: `{report.get('case_count', len(results))}`\n")
    lines.append(f"- Repository: `{report.get('repo_root', '')}`\n")
    lines.append(f"- Output directory: `{report.get('output_dir', '')}`\n")
    lines.append("\n")

    lines.append("## Cases\n")
    lines.append("| Case | Status | Return code | Report passed | Steps | CPU | NPU | GPU | Duration sec |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for result in results:
        counts = lane_counts(result.get("lanes"))
        lines.append(
            "| "
            + " | ".join(
                [
                    table_cell(result.get("name")),
                    case_status(result),
                    table_cell(result.get("returncode")),
                    bool_icon(result.get("report_passed")),
                    table_cell(result.get("step_count")),
                    table_cell(counts.get("CPU", 0)),
                    table_cell(counts.get("NPU", 0)),
                    table_cell(counts.get("GPU", 0)),
                    table_cell(result.get("duration_sec")),
                ]
            )
            + " |\n"
        )
    lines.append("\n")

    failed = [item for item in results if item.get("returncode") != 0 or item.get("report_passed") is not True]
    lines.append("## Failed or incomplete cases\n")
    if not failed:
        lines.append("No failed cases reported.\n\n")
    else:
        for item in failed:
            lines.append(f"### `{item.get('name')}`\n")
            lines.append(f"- Purpose: {item.get('purpose', '')}\n")
            lines.append(f"- Return code: `{item.get('returncode')}`\n")
            lines.append(f"- Report passed: `{bool_icon(item.get('report_passed'))}`\n")
            lines.append(f"- Report path: `{item.get('report_path', '')}`\n")
            if item.get("stderr_tail"):
                lines.append("\n```text\n")
                lines.append(str(item.get("stderr_tail"))[-2000:])
                lines.append("\n```\n")
            lines.append("\n")

    lines.append("## Individual report paths\n")
    for result in results:
        lines.append(f"- `{result.get('name')}`: `{result.get('report_path', '')}`\n")
    lines.append("\n")

    lines.append("## Notes\n")
    lines.append("- This report is generated from dry-run invocations only.\n")
    lines.append("- NPU, GPU, Blender and FFmpeg workloads are not executed by the matrix.\n")
    lines.append("- Inspect individual JSON reports for `summary`, `schedule`, `lanes` and `guardrail_remediation_loop`.\n")
    return "".join(lines)


def write_dry_run_matrix_markdown(path: str | Path, report: dict[str, Any]) -> Path:
    """Write a Markdown dry-run matrix report and return the output path."""
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dry_run_matrix_markdown(report), encoding="utf-8")
    return output
