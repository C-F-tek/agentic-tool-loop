"""Markdown rendering for provider telemetry semantic validation."""
from __future__ import annotations

from typing import Any


def render_validation(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Full0To10 provider telemetry semantic validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Patch application performed: `{report.get('patch_application_performed')}`",
        "",
        "## Reports",
        "",
    ]
    for name, item in (report.get("reports") or {}).items():
        lines.append(
            f"- `{name}` exists=`{item.get('exists')}` "
            f"kind_ok=`{item.get('kind_ok')}` passed=`{item.get('passed')}`"
        )
    lines.extend(["", "## Semantic flags", ""])
    for name, value in (report.get("semantic_flags") or {}).items():
        lines.append(f"- `{name}`: `{value}`")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{error}`")
    lines.append("")
    return "\n".join(lines)
