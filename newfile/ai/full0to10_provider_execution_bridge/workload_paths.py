"""Workload output path contract for provider execution bridge."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import SAFETY_FLAGS
from .paths import repo_relative


def build_workload_output_paths(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    workload_dir = output_dir / "future_real_run_outputs"
    paths = {
        "ollama_workload_report": workload_dir / "ollama_gpu_real_workload_report.md",
        "runtime_telemetry": workload_dir / "full0to10_provider_runtime_telemetry.json",
        "recommendations": workload_dir / "full0to10_provider_recommendations.json",
        "npu_audit_report": workload_dir / "full0to10_npu_after_run_audit.json",
        "quality_validation": workload_dir / "ai_workload_report_quality.json",
    }
    report = {
        "kind": "full0to10_provider_workload_output_paths",
        "passed": True,
        "workload_dir": repo_relative(workload_dir, repo_root),
        "paths": {role: repo_relative(path, repo_root) for role, path in paths.items()},
        "write_policy": {
            "future_real_run_only": True,
            "current_bridge_writes_placeholder": False,
            "output_root_only": True,
        },
        "validator_command": "python Tools/validation/check_ai_workload_report_quality.py --report-dir <workload_dir> --output <quality_validation>",
    }
    report.update(SAFETY_FLAGS)
    return report
