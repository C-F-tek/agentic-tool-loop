"""Markdown renderer for Full0To10 runtime tool registry."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 runtime tool registry",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Tool count: `{report['tool_count']}`",
        f"- Broker bridge ready: `{report['broker_bridge_ready']}`",
        "",
        "## Tools",
        "",
    ]
    for tool in report["tools"]:
        lines.append(
            f"- `{tool['name']}` category=`{tool['category']}` "
            f"writes_runtime_db=`{tool['writes_runtime_db']}`"
        )
    lines.append("")
    return "\n".join(lines)
