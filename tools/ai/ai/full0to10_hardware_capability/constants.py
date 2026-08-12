"""Constants for Full0To10 hardware/tool capability probes."""
from __future__ import annotations

REQUIRED_TOOL_PATHS = (
    "Tools/ai/agent_runtime_tool_broker.py",
    "Tools/ai/agent_runtime_sqlite_memory.py",
    "Tools/ai/build_runtime_tool_capability_manifest.py",
    "Tools/ai/build_runtime_tool_usage_telemetry.py",
    "Tools/ai/build_full0to10_run_manifest.py",
    "Tools/ai/build_shared_toolbox_ai_to_ai_bundle.py",
    "Tools/ai/run_agent_gpu_npu_parallel_orchestrator.py",
    "Tools/ai/run_agent_gpu_deep_planning_supervised.py",
    "Tools/ai/check_local_resource_lanes.py",
    "Tools/ai/check_npu_provider_environment.py",
    "Tools/validation/check_full0to10_bundle_contracts.py",
)

OPTIONAL_EXTERNAL_COMMANDS = (
    "ollama",
    "nvidia-smi",
)

DEFAULT_TIMEOUT_SECONDS = 8
