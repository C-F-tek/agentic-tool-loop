"""NPU audit hooks for provider invocation dry-run plan."""
from __future__ import annotations

from typing import Any

from .constants import AUDITOR_LANE, DIAGNOSTIC_LANE, SAFETY_FLAGS


def build_npu_audit_hooks(governor: dict[str, Any]) -> dict[str, Any]:
    npu_plan = governor.get("npu_audit") or {}
    hooks = {
        "kind": "full0to10_provider_npu_audit_hooks",
        "passed": True,
        "auditor_lane": AUDITOR_LANE,
        "diagnostic_lane": DIAGNOSTIC_LANE,
        "before_provider": [
            "verify permit",
            "verify evidence index",
            "verify GPU lane is primary only by permit",
        ],
        "after_provider": [
            "compare provider recommendations to memory evidence",
            "verify no patch apply occurred",
            "verify GPU.0 did not become primary",
            "verify telemetry completeness",
        ],
        "sample_count": npu_plan.get("audit_samples", {}).get("max_samples", 3),
        "promotion_allowed": False,
        "model_load_required_for_dry_run": False,
    }
    hooks.update(SAFETY_FLAGS)
    return hooks
