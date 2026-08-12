"""NPU audit plan for provider governor."""
from __future__ import annotations

from typing import Any


def build_npu_audit_plan(accelerator_control: dict[str, Any]) -> dict[str, Any]:
    npu = accelerator_control.get("npu_auditor") or {}
    gpu0 = accelerator_control.get("openvino_gpu0") or {}
    return {
        "kind": "full0to10_npu_audit_plan",
        "passed": True,
        "npu_role": npu.get("role", "sampled_auditor_or_diagnostic"),
        "npu_device_visible": npu.get("device_visible"),
        "gpu0_role": gpu0.get("role", "secondary_diagnostic_accelerator"),
        "audit_points": [
            "compare provider recommendation with memory/tool evidence",
            "check for missing telemetry",
            "check for excessive GPU claim",
            "check if GPU.0 tries to become primary",
            "check if patch plan is generated without explicit approval",
        ],
        "audit_samples": {
            "before_generation": True,
            "during_generation": False,
            "after_generation": True,
        },
        "promotion_allowed": False,
    }
