"""Path helpers for repo quality packet."""
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


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def excluded(path: Path, repo_root: Path) -> bool:
    rel = repo_relative(path, repo_root)
    parts = rel.replace(chr(92), "/").split("/")
    joined = "/".join(parts)
    return any(part in EXCLUDED_DIRS or joined.startswith(part + "/") for part in EXCLUDED_DIRS)


def under_output(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to((repo_root / "output").resolve())
        return True
    except ValueError:
        return False
