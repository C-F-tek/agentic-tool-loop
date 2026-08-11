"""Markdown renderer for provider governor."""
from __future__ import annotations

from typing import Any


def render_governor_markdown(governor: dict[str, Any]) -> str:
    permit = governor["run_permit"]
    lines = [
        "# Full0To10 provider governor",
        "",
        "## Request",
        "",
        governor["request"],
        "",
        "## Decision",
        "",
        f"- Permit allowed: `{permit['permit_allowed']}`",
        f"- Decision: `{permit['decision']}`",
        f"- Deny is failure: `{governor['deny_is_failure']}`",
        f"- Provider execution performed: `{governor['provider_execution_performed']}`",
        "",
        "A denied permit is a valid governor result. It means the run provider lane",
        "is blocked by policy, not that the tool failed.",
        "",
        "## Requirements",
        "",
    ]
    for item in governor["policy"]["requirements"]:
        lines.append(f"- `{item['requirement']}` passed=`{item['passed']}` — {item['reason']}")
    lines.extend(["", "## Budget", ""])
    for lane, budget in governor["budget"]["budgets"].items():
        lines.append(f"- `{lane}`: `{budget}`")
    lines.extend(["", "## NPU audit", ""])
    for point in governor["npu_audit"]["audit_points"]:
        lines.append(f"- {point}")
    lines.extend(["", "## Telemetry", ""])
    lines.append(f"- Events: `{governor['telemetry']['event_count']}`")
    lines.append(f"- Structural failures: `{governor['telemetry']['structural_failure_count']}`")
    lines.append(f"- Policy denial events: `{governor['telemetry']['policy_denial_event_count']}`")
    lines.extend(["", "## Next", ""])
    lines.append("Use this governor output as final-product evidence. A real provider run must still be invoked explicitly.")
    lines.append("")
    return "\n".join(lines)
