"""Constants for Full0To10 run manifests."""
from __future__ import annotations

DEFAULT_SCAN_ROOTS = (
    "docs/LOCAL_VALIDATION_EVIDENCE",
    "output/validation",
    "output/ai_pipeline",
    "output/ai_packets",
    "output/patch_specs",
    "output/semantic_chunks",
)

MEMORY_PATHS = (
    "output/ai_runtime_memory/operational_context.sqlite",
    "indexAI/agent_memory/agent_memory.sqlite",
)

DENY_CONTENT_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
)

DENY_CONTENT_FRAGMENTS = (
    "/renders/",
    "/indexAI/code_chunks/",
    "/indexAI/project_code_chunks/",
    "/output/ai_context_packs/",
    "full_analysis",
    "analysis_full",
)

ROLE_PATTERNS = {
    "csv_index_discovery": ("*line_count*.csv", "*script_inventory*.csv", "*markdown_inventory*.json"),
    "telemetry": ("*runtime_tool_usage_telemetry*.json", "*full_toolbox_run_telemetry_summary*.json"),
    "capability": ("*runtime_tool_capability_manifest*.json",),
    "provider_diagnostics": ("*parallel_gpu*.json", "*orchestrator*.json", "*gpu_npu*sync*.json"),
    "decision_loop": ("*decision_loop*.json",),
    "recommendations": ("*recommendations*.json",),
    "patch_plan": ("*patch_plan*.json",),
    "evidence_bundle": ("*shared_toolbox_ai_to_ai_bundle*.json", "*ai_to_ai_bundle*.json"),
}
