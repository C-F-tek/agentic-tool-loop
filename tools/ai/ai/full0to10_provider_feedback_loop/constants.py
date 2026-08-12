"""Constants for provider tool feedback loop report-only lane."""
from __future__ import annotations

REPORT_JSON = "full0to10_provider_tool_feedback_loop.json"
REPORT_MD = "full0to10_provider_tool_feedback_loop.md"
TOOL_OUTPUT_MANIFEST_JSON = "full0to10_provider_tool_output_manifest.json"
FEEDBACK_PACKET_JSON = "full0to10_provider_feedback_packet.json"

INPUT_REPORTS = (
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
)
