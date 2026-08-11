"""Collect Full0To10 quality stack reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import latest_matching, read_json, rel


REPORT_NAMES = {
    "hardware_capability": "full0to10_hardware_tool_capability.json",
    "runtime_tool_registry": "full0to10_runtime_tool_registry.json",
    "quality_gate": "full0to10_quality_gate.json",
    "run_manifest": "full0to10_run_manifest.json",
    "contract_validation": "full0to10_bundle_contract_validation.json",
}


def collect_report_paths(search_root: Path) -> dict[str, str | None]:
    output: dict[str, str | None] = {}
    for role, filename in REPORT_NAMES.items():
        match = latest_matching(search_root, filename)
        output[role] = str(match) if match else None
    return output


def collect_reports(search_root: Path) -> dict[str, Any]:
    paths = collect_report_paths(search_root)
    reports: dict[str, Any] = {}
    for role, path in paths.items():
        reports[role] = read_json(Path(path)) if path else None
    return {"paths": paths, "reports": reports}


def summarize_report_paths(paths: dict[str, str | None], repo_root: Path) -> dict[str, str | None]:
    return {role: rel(Path(path), repo_root) if path else None for role, path in paths.items()}
