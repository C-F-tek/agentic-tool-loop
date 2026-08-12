"""Parallel filesystem scanner for Full0To10 manifests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .constants import DENY_CONTENT_SUFFIXES


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    rel = repo_relative(path, repo_root)
    stat = path.stat()
    return {
        "path": rel,
        "suffix": suffix,
        "size_bytes": stat.st_size,
        "content_allowed": suffix not in DENY_CONTENT_SUFFIXES,
    }


def scan_root(repo_root: Path, root: Path) -> list[dict[str, object]]:
    resolved = root if root.is_absolute() else repo_root / root
    if not resolved.exists():
        return []
    return [
        file_record(path, repo_root)
        for path in resolved.rglob("*")
        if path.is_file()
    ]


def scan_roots(repo_root: Path, roots: list[Path], workers: int = 6) -> list[dict[str, object]]:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        chunks = list(executor.map(lambda item: scan_root(repo_root, item), roots))
    records = [record for chunk in chunks for record in chunk]
    return sorted(records, key=lambda item: str(item["path"]))
