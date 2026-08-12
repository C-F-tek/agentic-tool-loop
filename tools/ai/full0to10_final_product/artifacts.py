"""Artifact discovery and loading for Full0To10 final product."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import REQUIRED_PRODUCT_EVIDENCE
from .paths import repo_relative


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def product_artifacts(
    effective_dir: Path,
    quality_dir: Path,
    accelerator_dir: Path,
    governor_dir: Path,
    invocation_dir: Path,
    bridge_dir: Path,
    track_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    paths = {
        "effective_use_summary": effective_dir / "full0to10_effective_use_summary.json",
        "quality_product": effective_dir / "full0to10_effective_use_quality_product.md",
        "provider_hardening": effective_dir / "full0to10_provider_hardening_contracts.json",
        "tool_telemetry": effective_dir / "full0to10_effective_use_tool_telemetry.json",
        "optimization": effective_dir / "full0to10_effective_use_optimization.json",
        "quality_gate": quality_dir / "full0to10_quality_gate.json",
        "accelerator_control": accelerator_dir / "full0to10_accelerator_control.json",
        "provider_governor": governor_dir / "full0to10_provider_governor.json",
        "provider_run_permit": governor_dir / "full0to10_provider_run_permit.json",
        "provider_invocation_plan": invocation_dir / "full0to10_provider_invocation_plan.json",
        "provider_workload_report_contract": invocation_dir / "full0to10_provider_workload_report_contract.json",
        "provider_expected_telemetry_contract": invocation_dir / "full0to10_provider_expected_telemetry_contract.json",
        "provider_execution_bridge": bridge_dir / "full0to10_provider_execution_bridge.json",
        "provider_real_run_gate": bridge_dir / "full0to10_provider_real_run_gate.json",
        "provider_command_plan": bridge_dir / "full0to10_provider_command_plan.json",
        "provider_workload_output_paths": bridge_dir / "full0to10_provider_workload_output_paths.json",
        "track_input_contract": track_dir / "full0to10_track_input_contract.json",
        "track_input_template": track_dir / "full0to10_track_input_template.json",
    }
    records = {}
    for role, path in paths.items():
        records[role] = {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "type": "markdown" if path.suffix.lower() == ".md" else "json",
            "required": role in REQUIRED_PRODUCT_EVIDENCE,
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
        if path.suffix.lower() == ".json":
            records[role]["json"] = read_json(path)
    return records


def missing_required(records: dict[str, Any]) -> list[str]:
    return [role for role, record in records.items() if record.get("required") and not record.get("exists")]
