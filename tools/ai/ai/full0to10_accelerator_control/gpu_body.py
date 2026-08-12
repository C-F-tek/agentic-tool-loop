"""GPU body contract for Full0To10."""
from __future__ import annotations

from typing import Any

from .constants import GPU_BODY_DIMENSIONS


def build_gpu_body(capability: dict[str, Any]) -> dict[str, Any]:
    gpu = capability.get("gpu", {}) if isinstance(capability, dict) else {}
    command_available = gpu.get("command_available")
    body = {
        "kind": "gpu_body_contract",
        "role": "primary_compute_body_when_available",
        "owns": list(GPU_BODY_DIMENSIONS),
        "command_available": command_available,
        "device_query": gpu.get("device_query"),
        "driver_visible": bool(command_available),
        "memory_budget_policy": {
            "reserve_for_blender": True,
            "avoid_unbounded_context_growth": True,
            "prefer_telemetry_before_generation": True,
        },
        "process_ownership_policy": {
            "ollama_gpu_advisory_is_primary_when_enabled": True,
            "openvino_gpu0_secondary_until_promoted": True,
            "no_untracked_gpu_consumers": True,
        },
        "required_telemetry": [
            "gpu command availability",
            "provider lane using GPU",
            "generation enabled flag",
            "quality gate status",
        ],
    }
    body["passed"] = True
    return body
