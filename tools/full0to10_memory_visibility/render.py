"""Markdown rendering for memory visibility assertion."""
from __future__ import annotations

from typing import Any


def render_memory_visibility(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 memory visibility assertion",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- DB content read: `{report.get('db_content_read_performed')}`",
        f"- DB content included: `{report.get('db_content_included')}`",
        f"- Persistent memory write performed: `{report.get('persistent_memory_write_performed')}`",
        "",
        "## Memory paths",
        "",
        "| Name | Exists | Parent exists | Size bytes | Content included |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report.get("memory_paths", []):
        lines.append(
            f"| `{item.get('name')}` | `{item.get('exists')}` | "
            f"`{item.get('parent_exists')}` | `{item.get('size_bytes')}` | "
            f"`{item.get('content_included')}` |"
        )
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in report["warnings"]:
            lines.append(f"- `{warning}`")
    lines.append("")
    return "\n".join(lines)
