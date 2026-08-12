"""Markdown renderer for provider invocation plan."""
from __future__ import annotations

from typing import Any


def render_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 provider invocation dry-run plan",
        "",
        "## Request",
        "",
        plan["request"],
        "",
        "## Decision",
        "",
        f"- Provider lane: `{plan['provider_lane']}`",
        f"- Permit decision: `{plan['permit_decision']}`",
        f"- Generation executes now: `{plan['generation_executes_now']}`",
        f"- Ready for bundle inclusion: `{plan['readiness']['ready_for_bundle_inclusion']}`",
        "",
        "## Dry-run steps",
        "",
    ]
    for item in plan["dry_run_steps"]["steps"]:
        lines.append(f"{item['index']}. `{item['name']}` — {item['action']} executes_provider=`{item['executes_provider']}`")
    lines.extend(["", "## Required workload reports", ""])
    for report in plan["workload_report_contract"]["reports_required_after_real_run"]:
        lines.append(f"- `{report}`")
    lines.extend(["", "## Telemetry events", ""])
    for event in plan["expected_telemetry_contract"]["events_required"]:
        lines.append(f"- `{event}`")
    lines.extend(["", "## NPU audit hooks", ""])
    for hook in plan["npu_audit_hooks"]["after_provider"]:
        lines.append(f"- {hook}")
    lines.append("")
    return "\n".join(lines)
