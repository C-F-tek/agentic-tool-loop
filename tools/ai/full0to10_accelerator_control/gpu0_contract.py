"""OpenVINO GPU.0 contract for Full0To10."""
from __future__ import annotations

from typing import Any

from .device_visibility import openvino_visibility_summary


def build_gpu0_contract(capability: dict[str, Any]) -> dict[str, Any]:
    visibility = openvino_visibility_summary(capability)
    return {
        "kind": "openvino_gpu0_contract",
        "passed": True,
        "role": "secondary_diagnostic_accelerator",
        "device_visible": visibility["gpu0_visible"],
        "normalized_devices": visibility["devices"],
        "gpu_devices": visibility["gpu_devices"],
        "relationship_to_primary_gpu": "must_not_steal_ollama_gpu_lane",
        "allowed_actions": [
            "OpenVINO diagnostic",
            "capability listing",
            "secondary audit",
            "future promoted workload only with explicit patch",
        ],
        "blocked_actions": [
            "primary advisory default",
            "silent GPU provider takeover",
            "implicit generation",
        ],
    }
