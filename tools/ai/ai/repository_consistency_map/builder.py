"""Repository consistency report builder."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.ai.repository_consistency_map.constants import DOC_EXTENSIONS
from Tools.ai.repository_consistency_map.findings import build_findings, build_provider_hints
from Tools.ai.repository_consistency_map.markdown import extract_markdown_references
from Tools.ai.repository_consistency_map.paths import (
    bounded_worker_count,
    build_existing_path_index,
    elapsed_seconds,
    iter_files,
    now_iso,
)
from Tools.ai.repository_consistency_map.python_inventory import extract_python_inventory


def build_report(
    *,
    repo_root: Path,
    max_detail_items: int,
    max_snippet_chars: int,
    workers: int,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    timings: dict[str, float] = {}

    phase_started = time.perf_counter()
    markdown_file_count = len(iter_files(repo_root, DOC_EXTENSIONS))
    python_file_count = len(iter_files(repo_root, {".py"}))
    timings["file_discovery_seconds"] = elapsed_seconds(phase_started)

    phase_started = time.perf_counter()
    path_index = build_existing_path_index(repo_root)
    timings["path_index_seconds"] = elapsed_seconds(phase_started)

    phase_started = time.perf_counter()
    md_refs, md_commands, md_warnings = extract_markdown_references(
        repo_root,
        path_index,
        max_snippet_chars=max_snippet_chars,
        workers=workers,
    )
    timings["markdown_scan_seconds"] = elapsed_seconds(phase_started)

    phase_started = time.perf_counter()
    py_inventory, import_findings, py_warnings = extract_python_inventory(repo_root, workers=workers)
    timings["python_inventory_seconds"] = elapsed_seconds(phase_started)

    phase_started = time.perf_counter()
    findings = build_findings(
        md_refs=md_refs,
        md_commands=md_commands,
        py_inventory=py_inventory,
        import_findings=import_findings,
    )
    severity_counts = Counter(str(item.get("severity")) for item in findings)
    kind_counts = Counter(str(item.get("kind")) for item in findings)
    references_by_kind = Counter(str(item.get("kind")) for item in md_refs)
    provider_hints = build_provider_hints(findings)
    timings["findings_build_seconds"] = elapsed_seconds(phase_started)

    phase_started = time.perf_counter()
    scope = {
        "markdown_file_count": markdown_file_count,
        "python_file_count": python_file_count,
        "markdown_reference_count": len(md_refs),
        "markdown_python_command_count": len(md_commands),
        "python_inventory_count": len(py_inventory),
    }
    performance = {
        "workers_requested": workers,
        "markdown_scan_workers": bounded_worker_count(workers, markdown_file_count),
        "python_scan_workers": bounded_worker_count(workers, python_file_count),
        **timings,
    }
    performance["report_assembly_seconds"] = elapsed_seconds(phase_started)
    performance["total_build_report_seconds"] = elapsed_seconds(total_started)

    return {
        "schema_version": 1,
        "kind": "repository_consistency_map",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": md_warnings + py_warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "scope": {
            **scope,
            "generated_evidence_chunk_exclusion_enabled": True,
        },
        "finding_count": len(findings),
        "severity_counts": dict(sorted(severity_counts.items())),
        "finding_kind_counts": dict(sorted(kind_counts.items())),
        "markdown_reference_kind_counts": dict(sorted(references_by_kind.items())),
        "findings": findings,
        "markdown_references": md_refs[:max_detail_items] if max_detail_items else md_refs,
        "markdown_python_commands": md_commands[:max_detail_items] if max_detail_items else md_commands,
        "python_inventory": py_inventory,
        "provider_hints_for_gpu_planner": provider_hints,
        "performance": performance,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "do_not_commit_output": True,
            "generated_evidence_chunk_dirs_excluded": True,
        },
    }
