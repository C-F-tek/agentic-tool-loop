"""Markdown renderer for Markdown split shadow reports."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 Markdown split shadow apply",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Shadow root: `{report.get('shadow_root')}`",
        f"- Processed: `{report['processed_count']}`",
        f"- Accepted: `{report['accepted_count']}`",
        f"- Written files: `{report['written_file_count']}`",
        f"- Rejected: `{report['rejected_count']}`",
        "",
        "## Results",
        "",
    ]
    for item in report["results"][:60]:
        lines.append(f"- `{item['target_path']}` accepted=`{item['accepted']}` written=`{item['written']}`")
        if item.get("shadow_dir"):
            lines.append(f"  - shadow: `{item['shadow_dir']}`")
        if item.get("rejected_reason"):
            lines.append(f"  - rejected: {item['rejected_reason']}")
    lines.append("")
    return "\n".join(lines)
