"""Constants for Full0To10 provider execution bridge."""
from __future__ import annotations

BRIDGE_JSON = "full0to10_provider_execution_bridge.json"
GATE_JSON = "full0to10_provider_real_run_gate.json"
COMMAND_PLAN_JSON = "full0to10_provider_command_plan.json"
WORKLOAD_PATHS_JSON = "full0to10_provider_workload_output_paths.json"
TELEMETRY_JSON = "full0to10_provider_execution_bridge_telemetry.json"
BRIDGE_MD = "full0to10_provider_execution_bridge.md"

DEFAULT_REQUEST = (
    "Costruisci execution bridge gate per futura run GPU/Ollama con NPU audit, "
    "senza eseguire provider."
)

PRIMARY_PROVIDER = "ollama_gpu"
AUDITOR_PROVIDER = "openvino_npu"
DIAGNOSTIC_PROVIDER = "openvino_gpu0"

REAL_RUN_REQUIREMENTS = (
    "operator_intent",
    "allow_provider_generation",
    "permit_allowed",
    "dry_run_plan_ready",
    "workload_contract_ready",
    "telemetry_contract_ready",
    "npu_audit_hooks_ready",
    "quality_gate_acknowledged",
)

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
