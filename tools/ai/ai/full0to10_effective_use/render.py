"""Renderers for Full0To10 effective use optimization."""
from __future__ import annotations

from typing import Any


def render_summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 effective use optimization summary",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Quality product: `{report['outputs']['quality_product']}`",
        f"- Tool events: `{report['tool_telemetry']['event_count']}`",
        "",
        "## Scores",
        "",
    ]
    for key, value in report["optimization"]["scores"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Next actions", ""])
    for action in report["optimization"]["next_actions"]:
        lines.append(f"- {action}")
    lines.extend(["", "## Safety", ""])
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    return "\n".join(lines)
