"""Markdown rendering for provider tool feedback loop."""
from __future__ import annotations

from typing import Any


def render_provider_feedback(report: dict[str, Any]) -> str:
    manifest = report.get("tool_output_manifest") or {}
    packet = report.get("provider_feedback_packet") or {}
    lines = [
        "# Full0To10 provider tool feedback loop",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Feedback mode: `{packet.get('feedback_mode')}`",
        f"- Broker dry-run performed: `{packet.get('broker_dry_run_performed')}`",
        f"- Broker execution performed: `{packet.get('broker_execution_performed')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        "",
        "## Tool output manifest",
        "",
    ]
    for item in manifest.get("outputs", []):
        lines.append(
            f"- `{item.get('name')}` exists=`{item.get('exists')}` "
            f"kind_ok=`{item.get('kind_ok')}` passed=`{item.get('passed')}`"
        )
    lines.extend(["", "## Feedback items", ""])
    for item in packet.get("feedback_items", []):
        lines.append(f"- {item}")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{error}`")
    lines.append("")
    return "\n".join(lines)
