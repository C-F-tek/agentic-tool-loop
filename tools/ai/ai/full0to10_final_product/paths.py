"""Path helpers for Full0To10 final product."""
from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_path(repo_root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repo_root / value
