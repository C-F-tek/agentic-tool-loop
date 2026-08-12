"""Full0To10 quality gate report builder."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import build_quality_checks
from .constants import MAIN_OBJECTIVE
from .discover import find_reports, find_source_side_md_split_dirs, required_script_records
from .score import score_quality
from .split_advisory import load_specs, summarize_split_specs


def build_quality_gate(repo_root: Path, patch_specs: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    records = required_script_records(repo_root)
    source_side_dirs = find_source_side_md_split_dirs(repo_root)
    reports = find_reports(repo_root)
    checks = build_quality_checks(records, source_side_dirs, reports)
    split_advisory = summarize_split_specs(load_specs(patch_specs))
    readiness = score_quality(checks, split_advisory)
    return {
        "kind": "full0to10_quality_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not readiness["blockers"],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "repo_root": str(repo_root),
        "main_objective": list(MAIN_OBJECTIVE),
        "checks": checks,
        "split_advisory": split_advisory,
        "readiness": readiness,
        "errors": readiness["blockers"],
        "warnings": readiness["warnings"],
    }
