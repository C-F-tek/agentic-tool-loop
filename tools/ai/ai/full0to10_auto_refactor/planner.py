"""Full0To10 auto-refactor plan assembly."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .classify import classify_records
from .constants import DEFAULT_SCAN_ROOTS
from .hardware import build_hardware_candidates, build_hardware_contract
from .patch_specs import build_patch_specs
from .scan import scan_repo


def build_auto_refactor_plan(repo_root: Path, scan_roots: list[str] | None = None) -> dict[str, Any]:
    roots = scan_roots or list(DEFAULT_SCAN_ROOTS)
    records = scan_repo(repo_root.resolve(), roots)
    refactor_candidates = classify_records(records)
    hardware_candidates = build_hardware_candidates(records)
    candidates = refactor_candidates + hardware_candidates
    patch_specs = build_patch_specs(candidates)
    summary = Counter(str(item["kind"]) for item in candidates)
    return {
        "kind": "full0to10_auto_refactor_hardware_plan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "scan_roots": roots,
        "record_count": len(records),
        "candidate_count": len(candidates),
        "hardware_candidate_count": len(hardware_candidates),
        "patch_spec_count": len(patch_specs),
        "candidate_summary": dict(summary),
        "hardware_contract": build_hardware_contract(),
        "records": records,
        "candidates": candidates,
        "patch_specs": patch_specs,
        "errors": [],
        "warnings": [],
    }
