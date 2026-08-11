"""Constants for Full0To10 provider governor."""
from __future__ import annotations

GOVERNOR_JSON = "full0to10_provider_governor.json"
PERMIT_JSON = "full0to10_provider_run_permit.json"
TELEMETRY_JSON = "full0to10_provider_governor_telemetry.json"
GOVERNOR_MD = "full0to10_provider_governor.md"

DEFAULT_REQUEST = (
    "Valuta se GPU/Ollama può ricevere run permit con NPU auditor e GPU.0 "
    "diagnostic nel Full0To10."
)

PERMIT_REQUIREMENTS = (
    "operator_intent",
    "quality_gate_passed",
    "accelerator_scheduler_generation_blocked_pre_run",
    "gpu_mind_requires_launcher",
    "workload_quality_policy_available",
    "npu_audit_plan_available",
    "gpu0_guardrail_available",
)

PROVIDER_BUDGETS = {
    "ollama_gpu": {"max_minutes": 20, "max_rounds": 8, "max_new_tokens": 2400, "keep_alive": "20m"},
    "openvino_npu": {"max_samples": 3, "model_load_required": False, "audit_only": True},
    "openvino_gpu0": {"max_samples": 2, "diagnostic_only": True, "promotion_required": True},
}

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
