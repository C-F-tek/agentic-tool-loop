"""Constants for Full0To10 accelerator control plane."""
from __future__ import annotations

CONTROL_JSON = "full0to10_accelerator_control.json"
CONTROL_MD = "full0to10_accelerator_control.md"
TELEMETRY_JSON = "full0to10_accelerator_telemetry.json"

DEFAULT_REQUEST = (
    "Rendi GPU padrona del suo corpo e mente, con NPU auditor e GPU.0 diagnostic "
    "nel prodotto finale Full0To10."
)

LANES = ("gpu_body", "gpu_mind", "npu_auditor", "openvino_gpu0", "scheduler")

GPU_BODY_DIMENSIONS = (
    "device_visibility",
    "memory_budget",
    "thermal_and_driver_state",
    "process_ownership",
    "runtime_telemetry",
)

GPU_MIND_DIMENSIONS = (
    "advisory_policy",
    "provider_selection",
    "quality_gate_awareness",
    "fallback_reasoning",
    "no_implicit_generation",
)

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
