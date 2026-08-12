"""Markdown rendering for static code interpreter reports."""

from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    """Render compact Markdown summary."""
    lines = ["# Static Code Interpreter Report", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- File count: `{report['file_count']}`")
    lines.append(f"- Parsed files: `{report['parsed_file_count']}`")
    lines.append(f"- Total lines: `{report['total_lines']}`")
    lines.append(f"- Total functions: `{report['total_functions']}`")
    lines.append(f"- Total classes: `{report['total_classes']}`")
    lines.append(f"- Risk signals: `{report['total_risk_signals']}`")
    lines.append(f"- TODO/FIXME markers: `{report['total_todos']}`")
    lines.append(f"- Recommendation count: `{report['recommendation_count']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    lines.append("## Largest files")
    lines.append("")
    for item in report.get("largest_files", [])[:20]:
        lines.append(f"- `{item.get('path')}` - `{item.get('line_count')}` lines, risk `{item.get('risk')}`")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    recommendations = report.get("recommendations", [])
    if not recommendations:
        lines.append("- none")
    for item in recommendations[:40]:
        lines.append(f"- `{item.get('id')}` `{item.get('target_file')}` risk `{item.get('risk')}`: {', '.join(item.get('reasons') or ['no reason recorded'])}")
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This is static interpretation only. It does not execute repository code or apply changes.")
    return "\n".join(lines) + "\n"
