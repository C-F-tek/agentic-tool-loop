"""Expected telemetry contract for provider invocation plan."""
from __future__ import annotations

from typing import Any

from .constants import PRIMARY_PROVIDER_LANE, SAFETY_FLAGS


def build_expected_telemetry_contract(governor: dict[str, Any]) -> dict[str, Any]:
    budget = (governor.get("budget") or {}).get("budgets", {}).get(PRIMARY_PROVIDER_LANE, {})
    contract = {
        "kind": "full0to10_provider_expected_telemetry_contract",
        "passed": True,
        "provider_lane": PRIMARY_PROVIDER_LANE,
        "budget": budget,
        "events_required": [
            "provider_invocation_requested",
            "permit_loaded",
            "quality_gate_loaded",
            "gpu_capability_loaded",
            "prompt_or_context_bound",
            "provider_started",
            "provider_completed_or_failed",
            "workload_report_written",
            "runtime_telemetry_written",
            "npu_audit_scheduled",
        ],
        "fields_required": [
            "timestamp",
            "provider_lane",
            "model",
            "permit_decision",
            "generation_enabled",
            "duration_ms",
            "exit_code",
            "output_paths",
        ],
        "forbidden_flags": {
            "patch_application_performed": True,
            "blender_runtime_performed": True,
            "ffmpeg_runtime_performed": True,
        },
    }
    contract.update(SAFETY_FLAGS)
    return contract
