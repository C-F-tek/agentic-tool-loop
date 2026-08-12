"""Markdown rendering for Full0To10 final product quality package."""
from __future__ import annotations

from typing import Any


def render_quality_package(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# Full0To10 final product quality package",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Score: `{report.get('score')}`",
        f"- Ready for handoff: `{summary.get('ready_for_handoff')}`",
        f"- Ready for merge: `{summary.get('ready_for_merge')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Patch application performed: `{report.get('patch_application_performed')}`",
        "",
        "## Evidence reports",
        "",
        "| Name | Exists | JSON OK | Kind OK | Passed | Safety OK |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report.get("reports", []):
        lines.append(
            f"| `{item.get('name')}` | `{item.get('exists')}` | "
            f"`{item.get('json_ok')}` | `{item.get('kind_ok')}` | "
            f"`{item.get('passed')}` | `{item.get('safety_false_fields_ok')}` |"
        )
    if report.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for item in report["blockers"]:
            lines.append(f"- `{item}`")
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for item in report["warnings"]:
            lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)
