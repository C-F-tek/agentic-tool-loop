"""Markdown renderer for Full0To10 quality stack."""
from __future__ import annotations

from typing import Any


def render_markdown(summary: dict[str, Any]) -> str:
    readiness = summary["readiness"]
    lines = [
        "# Full0To10 quality stack preflight",
        "",
        f"- Passed: `{summary['passed']}`",
        f"- Score: `{readiness['score']}`",
        f"- Ready for real run: `{readiness['ready_for_real_run']}`",
        "",
        "## Report paths",
        "",
    ]
    for role, path in summary["report_paths"].items():
        lines.append(f"- `{role}`: `{path}`")

    lines.extend(["", "## Runtime tool summary", ""])
    for key, value in summary["runtime_tool_summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Hardware summary", ""])
    for key, value in summary["hardware_summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Blockers", ""])
    for item in readiness["blockers"] or ["None"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Warnings", ""])
    for item in readiness["warnings"] or ["None"]:
        lines.append(f"- {item}")

    lines.append("")
    return "\n".join(lines)
