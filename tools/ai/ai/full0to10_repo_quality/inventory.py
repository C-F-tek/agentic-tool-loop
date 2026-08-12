"""Repository inventory for quality packet."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import DEFAULT_SCAN_ROOTS, MAX_DEFAULT_FILES, TEXT_SUFFIXES
from .paths import excluded, repo_relative, resolve_path


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".py":
        return "python"
    if suffix == ".ps1":
        return "powershell"
    if suffix == ".json":
        return "json"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return "binary"


def iter_files(repo_root: Path, input_paths: list[str], max_files: int) -> list[Path]:
    raw_inputs = input_paths or list(DEFAULT_SCAN_ROOTS)
    files: list[Path] = []
    for raw in raw_inputs:
        path = resolve_path(repo_root, raw)
        if not path.exists():
            files.append(path)
            continue
        if path.is_file():
            files.append(path)
            continue
        for item in path.rglob("*"):
            if len(files) >= max_files:
                break
            if item.is_file() and not excluded(item, repo_root) and item.suffix.lower() in TEXT_SUFFIXES:
                files.append(item)
    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path.resolve())] = path
    return list(unique.values())[:max_files]


def build_inventory(repo_root: Path, input_paths: list[str], max_files: int) -> dict[str, Any]:
    items = []
    for path in iter_files(repo_root, input_paths, max_files):
        exists = path.exists() and path.is_file()
        stat = path.stat() if exists else None
        items.append(
            {
                "path": repo_relative(path, repo_root),
                "exists": exists,
                "kind": classify(path),
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size if stat else 0,
            }
        )
    return {
        "kind": "full0to10_repo_quality_inventory",
        "passed": all(item["exists"] for item in items),
        "file_count": len(items),
        "items": items,
        "counts_by_kind": counts_by_kind(items),
    }


def counts_by_kind(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        kind = str(item["kind"])
        counts[kind] = counts.get(kind, 0) + 1
    return counts
