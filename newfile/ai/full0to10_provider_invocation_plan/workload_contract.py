"""Workload report contract for provider invocation plan."""
from __future__ import annotations

from typing import Any

from .constants import EXPECTED_WORKLOAD_REPORTS, PRIMARY_PROVIDER_LANE, SAFETY_FLAGS


def build_workload_report_contract(governor: dict[str, Any]) -> dict[str, Any]:
    permit = governor.get("run_permit") or {}
    contract = {
        "kind": "full0to10_provider_workload_report_contract",
        "passed": True,
        "provider_lane": PRIMARY_PROVIDER_LANE,
        "permit_required": True,
        "permit_decision": permit.get("decision"),
        "permit_allowed": permit.get("permit_allowed"),
        "reports_required_after_real_run": list(EXPECTED_WORKLOAD_REPORTS),
        "minimum_content_requirements": [
            "provider lane",
            "model name",
            "GPU visibility",
            "input evidence references",
            "recommendations",
            "tool usage telemetry",
            "no patch applied flag",
        ],
        "quality_validator": "Tools/validation/check_ai_workload_report_quality.py --report-dir",
        "failure_policy": {
            "missing_report": "block_bundle_promotion",
            "unusable_report": "block_primary_advisory",
            "patch_application_detected": "hard_fail",
        },
        "notes": [
            "This contract does not execute provider generation.",
            "The real run must satisfy this contract before bundle promotion.",
        ],
    }
    contract.update(SAFETY_FLAGS)
    return contract
