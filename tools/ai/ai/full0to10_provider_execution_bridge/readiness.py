"""Readiness scoring for provider execution bridge."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def build_bridge_readiness(
    gate: dict[str, Any],
    command_plan: dict[str, Any],
    workload_paths: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    score = 100

    if not gate.get("passed"):
        blockers.append("real_run_gate_invalid")
        score -= 30
    if gate.get("real_run_allowed") is False:
        warnings.append("real_run_blocked_valid_pre_run_state")
        score -= 5
    if command_plan.get("all_commands_are_non_executing") is not True:
        blockers.append("command_plan_contains_executing_command")
        score -= 50
    if not workload_paths.get("passed"):
        blockers.append("workload_output_paths_invalid")
        score -= 20

    report = {
        "kind": "full0to10_provider_execution_bridge_readiness",
        "passed": not blockers,
        "score": max(0, score),
        "ready_for_final_product_inclusion": not blockers,
        "ready_for_real_provider_execution": bool(gate.get("real_run_allowed")) and not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }
    report.update(SAFETY_FLAGS)
    return report
