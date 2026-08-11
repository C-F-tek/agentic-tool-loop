"""Path helpers for track input contract."""
from __future__ import annotations

from pathlib import Path

from .constants import EXCLUDED_DIRS


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_excluded(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return any(excluded.lower() in parts for excluded in EXCLUDED_DIRS)


def existing_search_roots(repo_root: Path, roots: tuple[str, ...]) -> list[Path]:
    output: list[Path] = []
    for raw in roots:
        path = repo_root / raw
        if path.exists() and path.is_dir():
            output.append(path)
    return output
