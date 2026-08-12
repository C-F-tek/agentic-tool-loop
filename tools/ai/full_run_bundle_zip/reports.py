from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a compact Markdown completeness report."""
    lines = [
        "# Full0To10 evidence bundle completeness report",
        "",
        f"- Kind: `{report.get('kind')}`",
        f"- Passed: `{report.get('passed')}`",
        f"- Stamp: `{report.get('stamp')}`",
        f"- ZIP: `{report.get('zip_path')}`",
        f"- Included artifact count: `{report.get('included_artifact_count')}`",
        f"- ZIP member count: `{report.get('zip_member_count')}`",
        f"- Error count: `{len(report.get('errors') or [])}`",
        f"- Warning count: `{len(report.get('warnings') or [])}`",
        "",
        "## Errors",
        "",
    ]
    errors = report.get("errors") or []
    lines.extend([f"- {error}" for error in errors] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- none"])
    lines.extend(["", "## Included artifacts", ""])
    for item in report.get("artifacts", []):
        if item.get("included_in_zip"):
            lines.append(
                f"- `{item.get('path')}` members=`{item.get('zip_member_count')}` "
                f"source=`{item.get('source')}`"
            )
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    """Write JSON with repository-standard formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
