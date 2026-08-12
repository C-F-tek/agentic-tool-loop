"""Provider run permit builder."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def build_run_permit(
    policy: dict[str, Any],
    budget: dict[str, Any],
    npu_audit: dict[str, Any],
    allow_provider_generation: bool,
) -> dict[str, Any]:
    requirements = policy.get("requirements", [])
    failed = [item for item in requirements if not item.get("passed")]
    permit_allowed = bool(allow_provider_generation and not failed)
    decision = "allow_preview_only" if permit_allowed else "deny"
    permit = {
        "kind": "full0to10_provider_run_permit",
        "passed": True,
        "valid_result": True,
        "permit_allowed": permit_allowed,
        "allow_provider_generation_requested": allow_provider_generation,
        "decision": decision,
        "decision_is_failure": False,
        "failed_requirements": failed,
        "budget": budget,
        "npu_audit": npu_audit,
        "execution_contract": {
            "this_report_executes_provider": False,
            "future_provider_run_requires_this_permit": True,
            "provider_generation_must_write_workload_report": True,
            "provider_generation_must_write_tool_telemetry": True,
            "deny_is_valid_governor_result": True,
        },
        "errors": [],
        "warnings": [] if permit_allowed else ["permit denied by policy; artifact generation is still valid"],
    }
    permit.update(SAFETY_FLAGS)
    return permit
