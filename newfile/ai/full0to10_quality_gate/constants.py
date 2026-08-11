"""Constants for Full0To10 quality gate."""
from __future__ import annotations

REQUIRED_SCRIPTS = (
    "Tools/ai/full0to10_memory_tool.py",
    "Tools/ai/full0to10_runtime_tool.py",
    "Tools/ai/build_full0to10_runtime_tool_registry.py",
    "Tools/ai/build_full0to10_hardware_tool_capability.py",
    "Tools/ai/build_full0to10_run_manifest.py",
    "Tools/validation/check_full0to10_bundle_contracts.py",
    "Tools/workflow/run_full0to10_manifest_contract_gate.ps1",
    "Tools/workflow/run_unified_full0to10_with_contract_gate.ps1",
    "Tools/ai/build_full0to10_auto_refactor_plan.py",
    "Tools/ai/apply_full0to10_auto_refactor_patch_specs.py",
    "Tools/ai/apply_full0to10_markdown_split_patch_specs.py",
)

REPORT_PATTERNS = {
    "hardware_capability": "full0to10_hardware_tool_capability.json",
    "runtime_tool_registry": "full0to10_runtime_tool_registry.json",
    "sqlite_memory": "full0to10_sqlite_memory",
    "manifest_gate": "full0to10_run_manifest.json",
    "contract_gate": "full0to10_bundle_contract_validation.json",
}

MAIN_OBJECTIVE = (
    "SQLite FTS5 memory",
    "runtime tool usage",
    "GPU/Ollama readiness",
    "NPU/OpenVINO GPU.0 contract",
    "bundle telemetry/capability quality",
)
