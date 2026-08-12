"""Markdown renderer for provider execution bridge."""
from __future__ import annotations

from typing import Any


def render_bridge_markdown(bridge: dict[str, Any]) -> str:
    gate = bridge["real_run_gate"]
    lines = [
        "# Full0To10 provider execution bridge",
        "",
        "## Request",
        "",
        bridge["request"],
        "",
        "## Real-run gate",
        "",
        f"- Decision: `{gate['decision']}`",
        f"- Real run allowed: `{gate['real_run_allowed']}`",
        f"- Provider execution performed: `{bridge['provider_execution_performed']}`",
        "",
        "## Failed requirements",
        "",
    ]
    for item in gate["failed_requirements"] or [{"requirement": "None", "reason": ""}]:
        lines.append(f"- `{item['requirement']}` — {item.get('reason', '')}")
    lines.extend(["", "## Command plan", ""])
    for command in bridge["command_plan"]["commands"]:
        lines.append(f"- `{command['name']}` lane=`{command['provider_lane']}` would_execute=`{command['would_execute']}`")
    lines.extend(["", "## Workload output paths", ""])
    for role, path in bridge["workload_output_paths"]["paths"].items():
        lines.append(f"- `{role}`: `{path}`")
    lines.extend(["", "## Readiness", ""])
    lines.append(f"- Score: `{bridge['readiness']['score']}`")
    lines.append(f"- Ready for final product inclusion: `{bridge['readiness']['ready_for_final_product_inclusion']}`")
    lines.append(f"- Ready for real provider execution: `{bridge['readiness']['ready_for_real_provider_execution']}`")
    lines.append("")
    return "\n".join(lines)
