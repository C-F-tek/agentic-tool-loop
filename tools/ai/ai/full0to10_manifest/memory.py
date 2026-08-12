"""SQLite memory lane manifest helpers."""
from __future__ import annotations

from pathlib import Path

from .constants import MEMORY_PATHS
from .scan import repo_relative


def build_memory_manifest(repo_root: Path) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for rel in MEMORY_PATHS:
        path = repo_root / rel
        items.append(
            {
                "path": repo_relative(path, repo_root),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "content_included": False,
                "git_trackable": False,
            }
        )
    return {
        "scratch_memory_path": MEMORY_PATHS[0],
        "persistent_memory_path": MEMORY_PATHS[1],
        "persistent_memory_write_default": False,
        "sqlite_content_included": False,
        "items": items,
    }
