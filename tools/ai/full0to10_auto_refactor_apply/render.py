"""Markdown renderer for controlled refactor apply."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 controlled refactor apply",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Processed: `{report['processed_count']}`",
        f"- Changed: `{report['changed_count']}`",
        f"- Applied: `{report['applied_count']}`",
        f"- Rejected: `{report['rejected_count']}`",
        "",
        "## Results",
        "",
    ]
    for item in report["results"][:50]:
        lines.append(
            f"- `{item['candidate_kind']}` `{item['target_path']}` "
            f"changed=`{item['changed']}` applied=`{item['applied']}`"
        )
        if item.get("rejected_reason"):
            lines.append(f"  - rejected: {item['rejected_reason']}")
    lines.append("")
    return "\n".join(lines)
