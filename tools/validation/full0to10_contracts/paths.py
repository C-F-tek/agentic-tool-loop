"""Path collection for Full0To10 contract validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import LIST_PATH_KEYS, PATH_KEYS
from .io_utils import normalize_path_like, repo_relative


def _looks_path_like(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or value.endswith((".json", ".md", ".csv", ".txt", ".sqlite", ".db"))
    )


def collect_bundle_paths(bundle: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    stack: list[Any] = [bundle]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key in PATH_KEYS:
                value = current.get(key)
                if isinstance(value, str) and _looks_path_like(value):
                    paths.add(normalize_path_like(value))
            for key in LIST_PATH_KEYS:
                value = current.get(key)
                if isinstance(value, list):
                    stack.extend(value)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and _looks_path_like(current):
            paths.add(normalize_path_like(current))
    return sorted(paths)


def collect_evidence_paths(repo_root: Path, evidence_dir: Path | None) -> list[str]:
    if evidence_dir is None:
        return []
    resolved = evidence_dir if evidence_dir.is_absolute() else repo_root / evidence_dir
    if not resolved.exists():
        return []
    return sorted(repo_relative(path, repo_root) for path in resolved.rglob("*") if path.is_file())
