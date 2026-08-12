"""Markdown renderer for hardware/tool capability manifests."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 hardware/tool capability",
        "",
        f"- Passed: `{report['passed']}`",
        f"- External probes: `{report['external_probes_enabled']}`",
        f"- Missing tools: `{len(report['tool_inventory']['missing'])}`",
        "",
        "## Lanes",
        "",
        f"- Python: `{report['python']['executable']}`",
        f"- Ollama command available: `{report['ollama']['command_available']}`",
        f"- NVIDIA GPU command available: `{report['gpu']['command_available']}`",
        f"- NPU probe performed: `{report['npu']['probe_performed']}`",
        "",
        "## Errors",
        "",
    ]
    for error in report["errors"] or ["None"]:
        lines.append(f"- {error}")
    lines.extend(["", "## Warnings", ""])
    for warning in report["warnings"] or ["None"]:
        lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)
