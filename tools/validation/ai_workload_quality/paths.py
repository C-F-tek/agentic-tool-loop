"""Path helpers for AI workload quality validation."""
from __future__ import annotations

from pathlib import Path


def split_path_values(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                output.append(normalized)
    return output


def relative_or_absolute_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def packet_dirs(repo_root: Path, report_dir: Path) -> list[Path]:
    resolved = report_dir if report_dir.is_absolute() else repo_root / report_dir
    if not resolved.exists() or not resolved.is_dir():
        return [resolved]
    candidates = [resolved]
    try:
        candidates.extend(child for child in sorted(resolved.iterdir()) if child.is_dir())
    except OSError:
        pass
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).lower()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique
