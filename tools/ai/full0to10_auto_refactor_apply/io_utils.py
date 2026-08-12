"""I/O helpers for controlled refactor apply."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import TEXT_SUFFIXES


def load_patch_specs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("patch_specs"), list):
        return list(data["patch_specs"])
    if isinstance(data, list):
        return list(data)
    raise ValueError("patch specs JSON must be a list or object with patch_specs")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_target(repo_root: Path, target_path: str) -> Path:
    candidate = (repo_root / target_path).resolve()
    root = repo_root.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"target path escapes repository: {target_path}")
    if candidate.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError(f"unsupported text suffix: {candidate.suffix}")
    return candidate
