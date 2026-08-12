"""Constants for Full0To10 light provider telemetry semantic validation."""
from __future__ import annotations

REPORTS = {
    "accelerator_control": {
        "path": "accelerator_control/full0to10_accelerator_control.from_cli.json",
        "kind": "full0to10_accelerator_control",
    },
    "provider_governor": {
        "path": "provider_governor/full0to10_provider_governor.from_cli.json",
        "kind": "full0to10_provider_governor",
    },
    "provider_invocation_plan": {
        "path": "provider_invocation_plan/full0to10_provider_invocation_plan.from_cli.json",
        "kind": "full0to10_provider_invocation_plan",
    },
    "provider_execution_bridge": {
        "path": "provider_execution_bridge/full0to10_provider_execution_bridge.from_cli.json",
        "kind": "full0to10_provider_execution_bridge",
    },
}

SAFETY_FALSE_FIELDS = (
    "provider_execution_performed",
    "patch_application_performed",
    "source_writes_performed",
    "persistent_memory_write_performed",
    "blender_runtime_execution_performed",
    "ffmpeg_execution_performed",
)

REQUIRED_SEMANTIC_FLAGS = (
    "accelerator_has_npu_auditor",
    "accelerator_has_openvino_gpu0",
    "accelerator_external_probes_disabled",
    "accelerator_has_top_level_openvino_fields",
    "governor_has_run_permit",
    "governor_deny_not_failure",
    "invocation_generation_not_now",
    "invocation_has_telemetry_contract",
    "invocation_has_workload_contract",
    "bridge_real_run_gate_present",
    "bridge_command_plan_non_executing",
    "bridge_workload_paths_present",
    "gpu0_policy_visible",
    "npu_policy_visible",
)

REPORT_JSON = "full0to10_provider_telemetry_semantic_validation.json"
REPORT_MD = "full0to10_provider_telemetry_semantic_validation.md"
