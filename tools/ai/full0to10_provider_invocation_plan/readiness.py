"""Readiness for provider invocation dry-run plan."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def build_invocation_readiness(
    governor: dict[str, Any],
    workload_contract: dict[str, Any],
    telemetry_contract: dict[str, Any],
    dry_run_steps: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    score = 100

    if not governor.get("passed"):
        score -= 25
        blockers.append("provider_governor_not_passed")
    if not workload_contract.get("passed"):
        score -= 20
        blockers.append("workload_contract_not_passed")
    if not telemetry_contract.get("passed"):
        score -= 20
        blockers.append("telemetry_contract_not_passed")
    if dry_run_steps.get("generation_would_execute") is True:
        score -= 40
        blockers.append("dry_run_attempts_generation")

    permit = governor.get("run_permit") or {}
    if permit.get("permit_allowed") is False:
        warnings.append("permit_denied_valid_for_dry_run_plan")
    if permit.get("provider_execution_performed") is True:
        score -= 50
        blockers.append("permit_report_executed_provider")

    report = {
        "kind": "full0to10_provider_invocation_plan_readiness",
        "passed": not blockers,
        "score": max(0, score),
        "ready_for_bundle_inclusion": not blockers,
        "ready_for_real_generation": False,
        "blockers": blockers,
        "warnings": warnings,
    }
    report.update(SAFETY_FLAGS)
    return report
