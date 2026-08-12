"""Build AI workload quality validation reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .classifier import classify_report
from .paths import packet_dirs, relative_or_absolute_path
from .selector import collect_report_specs


def quality_decision(results: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [item["lane"] for item in results if item.get("usable")]
    unusable = [item["lane"] for item in results if not item.get("usable")]
    ollama_primary = any(item["lane"] == "ollama" and item.get("usable") for item in results)
    npu_usable = any(item["lane"] == "npu" and item.get("usable") for item in results)
    npu_excluded = any(
        item["lane"] == "npu" and not item.get("advisory_use", {}).get("allowed_as_advisory_context")
        for item in results
    )
    return {
        "usable_lanes": usable,
        "unusable_lanes": unusable,
        "ollama_gpu_primary_advisory_allowed": ollama_primary,
        "npu_report_text_usable": npu_usable,
        "npu_excluded_from_primary_advisory": npu_excluded,
        "provider_execution_seen": False,
        "source_writes_performed": False,
        "routing_policy": "selected_output_folder_workload_reports_only",
    }


def build_quality_report(
    repo_root: Path,
    report_specs: list[tuple[str, str]],
    selection_mode: str,
    report_dir: Path,
    unselected_known_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    results = []
    for lane, raw_path in report_specs:
        path = Path(raw_path)
        if not path.is_absolute():
            path = repo_root / path
        results.append(classify_report(path, lane=lane, repo_root=repo_root))

    errors = [f"{item['lane']}: {error}" for item in results for error in item.get("errors", [])]
    warnings = [f"{item['lane']}: {warning}" for item in results for warning in item.get("warnings", [])]
    unselected = list(unselected_known_reports or [])
    for item in unselected:
        warnings.append(f"{item.get('lane', 'unknown')}: known workload report not selected: {item.get('reason')}")

    if not results:
        warnings.append("no workload reports selected from output folder")

    usable = [item["lane"] for item in results if item.get("usable")]
    unusable = [item["lane"] for item in results if not item.get("usable")]
    return {
        "schema_version": 1,
        "kind": "ai_workload_report_quality",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "policy": "selected_output_folder_workload_reports_only",
        "mode": "report_only_workload_quality_gate",
        "selection_mode": selection_mode,
        "report_dir_cli_supported": True,
        "report_dir": relative_or_absolute_path(report_dir, repo_root),
        "packet_dirs": [relative_or_absolute_path(item, repo_root) for item in packet_dirs(repo_root, report_dir)],
        "selected_reports": [{"lane": lane, "path": relative_or_absolute_path(Path(path), repo_root)} for lane, path in report_specs],
        "unselected_known_reports": unselected,
        "usable_lanes": usable,
        "unusable_lanes": unusable,
        "decision": quality_decision(results),
        "checks": {"report_count": len(results), "usable_count": len(usable), "unusable_count": len(unusable), "results": results},
    }


def from_report_dir(repo_root: Path, report_dir: Path, include_missing: bool) -> dict[str, Any]:
    specs, unselected = collect_report_specs(repo_root, report_dir, include_missing)
    mode = "output_folder_with_missing_known_reports" if include_missing else "output_folder"
    return build_quality_report(repo_root, specs, mode, report_dir, unselected)
