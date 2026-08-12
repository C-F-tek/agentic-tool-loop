"""Markdown renderer for Full0To10 SQLite memory reports."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 SQLite memory report",
        "",
        f"- Kind: `{report.get('kind')}`",
        f"- Passed: `{report.get('passed')}`",
        f"- Namespace: `{report.get('namespace')}`",
        "",
    ]
    if "item_count" in report:
        lines.append(f"- Items: `{report.get('item_count')}`")
        lines.append(f"- Chunks: `{report.get('chunk_count')}`")
        lines.append(f"- Embedding cache entries: `{report.get('embedding_cache_count')}`")
    if "result_count" in report:
        lines.append(f"- Results: `{report.get('result_count')}`")
    lines.append("")
    return "\n".join(lines)
