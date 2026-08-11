"""Build Full0To10 quality stack summary."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .collector import collect_reports, summarize_report_paths
from .score import compute_readiness, hardware_summary, runtime_tool_summary


def build_quality_stack_summary(repo_root: Path, search_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    search_root = search_root.resolve()
    collected = collect_reports(search_root)
    reports = collected["reports"]
    readiness = compute_readiness(reports)
    return {
        "kind": "full0to10_quality_stack_preflight",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not readiness["blockers"],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "repo_root": str(repo_root),
        "search_root": str(search_root),
        "report_paths": summarize_report_paths(collected["paths"], repo_root),
        "runtime_tool_summary": runtime_tool_summary(reports.get("runtime_tool_registry")),
        "hardware_summary": hardware_summary(reports.get("hardware_capability")),
        "quality_gate": reports.get("quality_gate"),
        "readiness": readiness,
        "errors": readiness["blockers"],
        "warnings": readiness["warnings"],
    }
