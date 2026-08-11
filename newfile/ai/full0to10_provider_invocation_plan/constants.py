"""Constants for provider invocation dry-run plan."""
from __future__ import annotations

PLAN_JSON = "full0to10_provider_invocation_plan.json"
PLAN_MD = "full0to10_provider_invocation_plan.md"
WORKLOAD_CONTRACT_JSON = "full0to10_provider_workload_report_contract.json"
TELEMETRY_CONTRACT_JSON = "full0to10_provider_expected_telemetry_contract.json"
DRY_RUN_STEPS_JSON = "full0to10_provider_dry_run_steps.json"

DEFAULT_REQUEST = (
    "Pianifica dry-run provider GPU/Ollama con NPU audit e workload report "
    "contract, senza generazione reale."
)

PRIMARY_PROVIDER_LANE = "ollama_gpu"
AUDITOR_LANE = "openvino_npu"
DIAGNOSTIC_LANE = "openvino_gpu0"

EXPECTED_WORKLOAD_REPORTS = (
    "ollama_gpu_real_workload_report.md",
    "full0to10_provider_runtime_telemetry.json",
    "full0to10_provider_recommendations.json",
)

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
