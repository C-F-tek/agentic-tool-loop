"""Build report-only SQLite/memory visibility assertions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import MEMORY_PATHS


def _entry(repo_root: Path, spec: dict[str, str]) -> dict[str, Any]:
    path = repo_root / spec["path"]
    parent = path.parent
    exists = path.exists()
    stat = path.stat() if exists and path.is_file() else None
    return {
        "name": spec["name"],
        "role": spec["role"],
        "path": spec["path"],
        "absolute_path": str(path),
        "parent_exists": parent.exists(),
        "exists": exists,
        "is_file": path.is_file(),
        "size_bytes": stat.st_size if stat else 0,
        "content_read_performed": False,
        "content_included": False,
        "write_performed": False,
    }


def build_memory_visibility_assertion(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    entries = [_entry(repo_root, spec) for spec in MEMORY_PATHS]
    warnings = [f"memory_path_missing:{item['name']}" for item in entries if not item["exists"]]
    return {
        "kind": "full0to10_memory_visibility_assertion",
        "passed": True,
        "repo_root": str(repo_root),
        "memory_paths": entries,
        "db_content_included": False,
        "db_content_read_performed": False,
        "persistent_memory_write_performed": False,
        "source_writes_performed": False,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "errors": [],
        "warnings": warnings,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
