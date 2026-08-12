"""Real-run gate for provider execution bridge."""
from __future__ import annotations

from typing import Any

from .constants import REAL_RUN_REQUIREMENTS, SAFETY_FLAGS


def requirement(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"requirement": name, "passed": passed, "reason": reason}


def build_real_run_gate(
    invocation_plan: dict[str, Any],
    operator_intent: bool,
    allow_provider_generation: bool,
) -> dict[str, Any]:
    permit_allowed = bool(invocation_plan.get("permit_allowed"))
    readiness = invocation_plan.get("readiness") or {}
    reqs = [
        requirement("operator_intent", operator_intent, "explicit operator intent required"),
        requirement("allow_provider_generation", allow_provider_generation, "real generation flag required"),
        requirement("permit_allowed", permit_allowed, "provider run permit must allow generation"),
        requirement("dry_run_plan_ready", bool(readiness.get("ready_for_bundle_inclusion")), "dry-run plan must be bundle-ready"),
        requirement("workload_contract_ready", bool(invocation_plan.get("workload_report_contract", {}).get("passed")), "workload report contract must pass"),
        requirement("telemetry_contract_ready", bool(invocation_plan.get("expected_telemetry_contract", {}).get("passed")), "telemetry contract must pass"),
        requirement("npu_audit_hooks_ready", bool(invocation_plan.get("npu_audit_hooks", {}).get("passed")), "NPU audit hooks must pass"),
        requirement("quality_gate_acknowledged", True, "quality gate is captured as evidence, not overridden"),
    ]
    known = {item["requirement"] for item in reqs}
    for name in REAL_RUN_REQUIREMENTS:
        if name not in known:
            reqs.append(requirement(name, False, "requirement not produced"))

    gate_allowed = all(item["passed"] for item in reqs)
    report = {
        "kind": "full0to10_provider_real_run_gate",
        "passed": True,
        "real_run_allowed": gate_allowed,
        "real_run_requested": allow_provider_generation,
        "requirements": reqs,
        "failed_requirements": [item for item in reqs if not item["passed"]],
        "decision": "allow_future_real_run" if gate_allowed else "block_real_run",
        "deny_is_failure": False,
        "errors": [],
        "warnings": [] if gate_allowed else ["real provider run blocked by gate"],
    }
    report.update(SAFETY_FLAGS)
    return report
