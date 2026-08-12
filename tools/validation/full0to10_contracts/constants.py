"""Constants for Full0To10 contract validation."""
from __future__ import annotations

REQUIRED_BUNDLE_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workflow_report", ("*workflow*.json", "*full_toolbox*decision_loop*.json")),
    ("orchestrator_raw_report", ("*orchestrator*.json",)),
    ("gpu_raw_report", ("*parallel_gpu*.json", "*gpu*.json")),
    ("gpu_npu_sync_diagnostics", ("*gpu_npu*sync*.json", "*gpu*npu*.json")),
    ("repository_consistency_map", ("*repository_consistency_map*.json",)),
    ("repository_consistency_smoke", ("*repository_consistency*smoke*.json",)),
    ("decision_loop_report", ("*decision_loop*.json",)),
    (
        "deterministic_recommendations",
        ("*deterministic_recommendations*.json", "*recommendations*.json"),
    ),
    ("patch_plan", ("*patch_plan*.json",)),
    ("runtime_tool_usage_telemetry", ("*runtime_tool_usage_telemetry*.json",)),
    ("runtime_tool_capability_manifest", ("*runtime_tool_capability_manifest*.json",)),
    (
        "full_toolbox_run_telemetry_summary",
        ("*full_toolbox_run_telemetry_summary*.json", "*telemetry_summary*.json"),
    ),
    ("semantic_chunk_manifest", ("*semantic*chunk*manifest*.json", "*chunk*manifest*.json")),
    (
        "shared_toolbox_ai_to_ai_bundle",
        ("*shared_toolbox_ai_to_ai_bundle*.json", "*ai_to_ai_bundle*.json"),
    ),
)

EXPECTED_MEMORY_PATHS = (
    "output/ai_runtime_memory/operational_context.sqlite",
    "indexAI/agent_memory/agent_memory.sqlite",
)

DB_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm")
PATH_KEYS = ("path", "source", "bundle", "markdown_output", "json_output", "output", "report")
LIST_PATH_KEYS = (
    "artifact_manifest",
    "source_included_artifacts",
    "source_artifacts",
    "evidence_to_commit",
    "reports",
    "phase_reports",
)
