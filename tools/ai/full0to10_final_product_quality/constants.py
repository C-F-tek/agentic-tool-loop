"""Constants for Full0To10 final product quality package."""
from __future__ import annotations

REPORT_JSON = "full0to10_final_product_quality_package.json"
REPORT_MD = "full0to10_final_product_quality_package.md"
SUMMARY_JSON = "full0to10_final_product_quality_summary.json"

REQUIRED_REPORTS = (
    {
        "name": "startup_guard",
        "path": "startup/startup_check.json",
        "kind": "startup_check",
    },
    {
        "name": "track_inputs",
        "path": "track_inputs/full0to10_track_input_contract.from_cli.json",
        "kind": "full0to10_track_input_contract",
    },
    {
        "name": "repo_quality",
        "path": "repo_quality/full0to10_repo_quality_packet.from_cli.json",
        "kind": "full0to10_repo_quality_packet",
    },
    {
        "name": "accelerator_control",
        "path": "accelerator_control/full0to10_accelerator_control.from_cli.json",
        "kind": "full0to10_accelerator_control",
    },
    {
        "name": "provider_governor",
        "path": "provider_governor/full0to10_provider_governor.from_cli.json",
        "kind": "full0to10_provider_governor",
    },
    {
        "name": "provider_invocation_plan",
        "path": "provider_invocation_plan/full0to10_provider_invocation_plan.from_cli.json",
        "kind": "full0to10_provider_invocation_plan",
    },
    {
        "name": "provider_execution_bridge",
        "path": "provider_execution_bridge/full0to10_provider_execution_bridge.from_cli.json",
        "kind": "full0to10_provider_execution_bridge",
    },
    {
        "name": "provider_telemetry_semantic",
        "path": "provider_telemetry_semantic/full0to10_provider_telemetry_semantic_validation.json",
        "kind": "full0to10_provider_telemetry_semantic_validation",
    },
    {
        "name": "memory_visibility_assertion",
        "path": "memory_visibility/full0to10_memory_visibility_assertion.json",
        "kind": "full0to10_memory_visibility_assertion",
    },
    {
        "name": "provider_tool_feedback_loop",
        "path": "provider_tool_feedback_loop/full0to10_provider_tool_feedback_loop.json",
        "kind": "full0to10_provider_tool_feedback_loop",
    },
    {
        "name": "final_tool_product",
        "path": "final_product.from_cli.json",
        "kind": "full0to10_final_tool_product_manifest",
    },
)

SAFETY_FALSE_FIELDS = (
    "provider_execution_performed",
    "patch_application_performed",
    "source_writes_performed",
    "persistent_memory_write_performed",
    "blender_runtime_execution_performed",
    "ffmpeg_execution_performed",
)
