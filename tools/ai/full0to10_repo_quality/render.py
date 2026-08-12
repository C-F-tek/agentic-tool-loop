"""Markdown renderer for repo quality packet."""
from __future__ import annotations

from typing import Any


def render_packet(packet: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 repository quality packet",
        "",
        f"- Request: `{packet['request']}`",
        f"- Tool: `{packet['tool_plan']['tool']}`",
        f"- Passed: `{packet['passed']}`",
        f"- Files scanned: `{packet['inventory']['file_count']}`",
        "",
        "## Counts by kind",
        "",
    ]
    for kind, count in sorted(packet["inventory"]["counts_by_kind"].items()):
        lines.append(f"- `{kind}`: `{count}`")
    lines.extend(["", "## Findings", ""])
    for item in packet["findings"]["findings"]:
        lines.append(f"- `{item['severity']}` `{item['code']}` — {item['message']}")
    lines.extend(["", "## Tool routes", ""])
    for route in packet["tool_plan"]["routes"]:
        lines.append(f"- `{route}`")
    lines.extend(["", "## Representative files", ""])
    for item in packet["inventory"]["items"][:30]:
        lines.append(f"- `{item['path']}` kind=`{item['kind']}` size=`{item['size_bytes']}`")
    lines.append("")
    return "\n".join(lines)
