"""Markdown rendering for Full0To10 contract reports."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 bundle contract validation",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Bundle: `{report['inputs'].get('bundle')}`",
        f"- Evidence dir: `{report['inputs'].get('evidence_dir')}`",
        f"- Path count: `{report['path_count']}`",
        "",
        "## Required bundle roles",
        "",
    ]
    for item in report["required_roles"]:
        lines.append(f"- `{item['role']}`: `{item['passed']}` matches=`{len(item['matches'])}`")

    lines.extend(["", "## SQLite memory contract", ""])
    for key, value in report["memory_contract"].items():
        if key not in {"errors", "warnings", "db_content_violations"}:
            lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Hardware delegation contract", ""])
    for key, value in report["hardware_contract"].items():
        if key not in {"errors", "warnings"}:
            lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Errors", ""])
    for error in report["errors"] or ["None"]:
        lines.append(f"- {error}")

    lines.extend(["", "## Warnings", ""])
    for warning in report["warnings"] or ["None"]:
        lines.append(f"- {warning}")

    lines.append("")
    return "\n".join(lines)
