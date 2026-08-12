"""NPU auditor contract for Full0To10."""
from __future__ import annotations

from typing import Any

from .device_visibility import openvino_visibility_summary


def build_npu_auditor(capability: dict[str, Any]) -> dict[str, Any]:
    npu = capability.get("npu", {}) if isinstance(capability, dict) else {}
    visibility = openvino_visibility_summary(capability)
    return {
        "kind": "npu_auditor_contract",
        "passed": True,
        "role": "sampled_auditor_or_diagnostic",
        "device_visible": visibility["npu_visible"],
        "normalized_devices": visibility["devices"],
        "probe_performed": npu.get("probe_performed"),
        "allowed_actions": [
            "sampled review",
            "diagnostic evidence",
            "provider disagreement audit",
            "quality gate cross-check",
        ],
        "blocked_actions": [
            "primary advisory by default",
            "implicit model loading",
            "patch application",
            "runtime generation without explicit promotion",
        ],
        "promotion_requirements": [
            "dedicated patch",
            "smoke evidence",
            "quality stack approval",
            "operator explicit request",
        ],
    }
