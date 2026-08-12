"""Provider command plan for future real run."""
from __future__ import annotations

from typing import Any

from .constants import AUDITOR_PROVIDER, DIAGNOSTIC_PROVIDER, PRIMARY_PROVIDER, SAFETY_FLAGS


def build_command_plan(invocation_plan: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    telemetry_contract = invocation_plan.get("expected_telemetry_contract") or {}
    budget = telemetry_contract.get("budget") or {}
    commands = [
        {
            "name": "ollama_gpu_primary_advisory",
            "provider_lane": PRIMARY_PROVIDER,
            "would_execute": False,
            "requires_gate_allowed": True,
            "budget": budget,
            "expected_outputs": invocation_plan.get("workload_report_contract", {}).get("reports_required_after_real_run", []),
        },
        {
            "name": "npu_after_run_audit",
            "provider_lane": AUDITOR_PROVIDER,
            "would_execute": False,
            "requires_primary_output": True,
            "audit_hooks": invocation_plan.get("npu_audit_hooks", {}).get("after_provider", []),
        },
        {
            "name": "gpu0_diagnostic_probe",
            "provider_lane": DIAGNOSTIC_PROVIDER,
            "would_execute": False,
            "requires_promotion": True,
            "reason": "GPU.0 remains secondary diagnostic",
        },
    ]
    report = {
        "kind": "full0to10_provider_command_plan",
        "passed": True,
        "real_run_gate_decision": gate["decision"],
        "commands": commands,
        "all_commands_are_non_executing": all(not item["would_execute"] for item in commands),
        "future_execution_flag_required": True,
    }
    report.update(SAFETY_FLAGS)
    return report
