"""Readiness scoring for Full0To10 final tool product."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def contract_passed(record: dict[str, Any]) -> bool:
    data = record.get("json")
    return bool(isinstance(data, dict) and data.get("passed") is True)


def build_readiness(records: dict[str, Any], evidence_index: dict[str, Any]) -> dict[str, Any]:
    score = 100
    blockers: list[str] = []
    warnings: list[str] = []

    if not evidence_index["passed"]:
        score -= 35
        blockers.extend(evidence_index["missing_required_roles"])

    json_roles = (
        "effective_use_summary",
        "provider_hardening",
        "tool_telemetry",
        "optimization",
        "quality_gate",
        "accelerator_control",
        "provider_governor",
        "provider_run_permit",
        "provider_invocation_plan",
        "provider_workload_report_contract",
        "provider_expected_telemetry_contract",
        "provider_execution_bridge",
        "provider_real_run_gate",
        "provider_command_plan",
    )
    for role in json_roles:
        record = records.get(role, {})
        if record.get("exists") and record.get("type") == "json" and not contract_passed(record):
            score -= 8
            warnings.append(f"{role}_not_passed")

    track = records.get("track_input_contract", {}).get("json") or {}
    if track:
        if track.get("complete") is not True:
            warnings.append("track_input_contract_incomplete")
        if track.get("passed") is not True:
            warnings.append("track_input_contract_not_passed")

    bridge = records.get("provider_execution_bridge", {}).get("json") or {}
    if bridge.get("provider_execution_performed") is True:
        score -= 50
        blockers.append("provider_execution_bridge_executed_provider")

    command = records.get("provider_command_plan", {}).get("json") or {}
    if command.get("all_commands_are_non_executing") is not True:
        score -= 40
        blockers.append("provider_command_plan_contains_executing_command")

    score = max(0, score)
    report = {
        "kind": "full0to10_final_tool_product_readiness",
        "passed": not blockers,
        "score": score,
        "ready_for_tool_product_review": score >= 80 and not blockers,
        "ready_for_real_provider_run": False,
        "blockers": blockers,
        "warnings": warnings,
        "policy": "final_product_review_before_real_provider_run",
    }
    report.update(SAFETY_FLAGS)
    return report
