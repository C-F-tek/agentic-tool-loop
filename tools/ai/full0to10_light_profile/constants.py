"""Constants for Full0To10 light profile promotion."""
from __future__ import annotations

PROMOTION_JSON = "full0to10_light_profile_promotion.json"
PROMOTION_MD = "full0to10_light_profile_promotion.md"
NEXT_LOOP_JSON = "full0to10_light_profile_next_loop.json"

REQUIRED_STEPS = (
    "startup_guard",
    "track_inputs",
    "repo_quality",
    "markdown_line_limit",
    "accelerator_control",
    "provider_governor",
    "provider_invocation_plan",
    "provider_execution_bridge",
    "provider_telemetry_semantic",
    "memory_visibility_assertion",
    "provider_tool_feedback_loop",
    "final_product_quality_package",
)

SAFETY_FALSE_FIELDS = (
    "provider_execution_performed",
    "patch_application_performed",
    "blender_runtime_execution_performed",
    "ffmpeg_execution_performed",
)

NEXT_LOOP_ACTIONS = (
    "wire LightFull0To10 flag into unified launcher",
    "keep NoExternalProbes default for light profile",
    "add provider telemetry semantic validator",
    "add GPU.0/NPU normalized device visibility check",
    "add provider tool feedback loop report-only",
    "finalize LightFull0To10 product quality package",
)
