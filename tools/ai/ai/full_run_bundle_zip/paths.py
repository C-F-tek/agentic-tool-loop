from __future__ import annotations

from pathlib import Path


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a normalized repository-relative path when possible."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    """Resolve a CLI path relative to repo_root when it is not absolute."""
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def split_values(values: list[str] | None) -> list[str]:
    """Split repeatable comma-separated CLI values."""
    out: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            item = part.strip().strip("'\"")
            if item and item not in out:
                out.append(item)
    return out
