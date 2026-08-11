"""Evidence index builder for final tool product."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import missing_required
from .constants import SAFETY_FLAGS
from .paths import repo_relative


def build_evidence_index(repo_root: Path, records: dict[str, Any]) -> dict[str, Any]:
    missing = missing_required(records)
    usable = [role for role, record in records.items() if record.get("exists")]
    total_size = sum(int(record.get("size_bytes") or 0) for record in records.values())
    report = {
        "kind": "full0to10_final_tool_product_evidence_index",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not missing,
        "repo_root": str(repo_root),
        "usable_evidence_roles": usable,
        "missing_required_roles": missing,
        "total_size_bytes": total_size,
        "artifacts": records,
        "errors": [f"missing required evidence: {role}" for role in missing],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    return report


def output_record(path: Path, repo_root: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": repo_relative(path, repo_root),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }
