"""Discovery helpers for Full0To10 quality gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import REQUIRED_SCRIPTS


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def required_script_records(repo_root: Path) -> list[dict[str, Any]]:
    records = []
    for rel in REQUIRED_SCRIPTS:
        path = repo_root / rel
        records.append(
            {
                "path": rel,
                "exists": path.exists(),
                "lines": path.read_text(encoding="utf-8", errors="replace").count("\n") if path.exists() else None,
            }
        )
    return records


def find_source_side_md_split_dirs(repo_root: Path) -> list[str]:
    results = []
    for path in repo_root.rglob("*.md.split"):
        if not path.is_dir():
            continue
        rel = repo_relative(path, repo_root)
        if rel.startswith("output/validation/"):
            continue
        results.append(rel)
    return sorted(results)


def find_reports(repo_root: Path) -> list[str]:
    roots = [repo_root / "output" / "validation", repo_root / "docs" / "LOCAL_VALIDATION_EVIDENCE"]
    reports = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            reports.append(repo_relative(path, repo_root))
    return sorted(reports)
