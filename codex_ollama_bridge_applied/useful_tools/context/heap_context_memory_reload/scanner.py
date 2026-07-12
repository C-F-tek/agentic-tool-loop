"""Repository scanning helpers for heap startup reload."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ia_carmine.context.heap_context_memory_reload.common import (
    CANONICAL_CONTEXT_FILES,
    REPO_SCAN_EXCLUDED_DIRS,
    REPO_SCAN_TEXT_SUFFIXES,
    repo_rel,
)


def is_repo_scan_excluded(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    for excluded in REPO_SCAN_EXCLUDED_DIRS:
        excluded = excluded.strip("/")
        if not excluded:
            continue
        if "/" in excluded:
            if normalized == excluded or normalized.startswith(excluded + "/"):
                return True
        elif excluded in parts:
            return True
    return False


def repo_scan_files(
    repo_root: Path, *, max_files: int, suffixes: set[str] | None = None
) -> list[Path]:
    suffix_filter = suffixes or REPO_SCAN_TEXT_SUFFIXES
    files: list[Path] = []
    for root, dirs, names in os.walk(repo_root):
        root_path = Path(root)
        dirs[:] = [
            dirname
            for dirname in dirs
            if not is_repo_scan_excluded(repo_rel(repo_root, root_path / dirname))
        ]
        for name in names:
            path = root_path / name
            rel_path = repo_rel(repo_root, path)
            if is_repo_scan_excluded(rel_path):
                continue
            if path.suffix.lower() not in suffix_filter:
                continue
            files.append(path)
            if len(files) >= max_files:
                return sorted(files, key=lambda item: repo_rel(repo_root, item).lower())
    return sorted(files, key=lambda item: repo_rel(repo_root, item).lower())


def repo_scan_context_files(repo_root: Path, *, max_files: int) -> list[str]:
    priority_names = {"AGENTS.md", "README.md", "WORKFLOW.md"}
    selected: list[str] = []
    for rel_path in CANONICAL_CONTEXT_FILES:
        if (repo_root / rel_path).is_file() and rel_path not in selected:
            selected.append(rel_path)
    for path in repo_scan_files(repo_root, max_files=max_files, suffixes={".md"}):
        rel_path = repo_rel(repo_root, path)
        if path.name in priority_names or rel_path.startswith("docs/"):
            if rel_path not in selected:
                selected.append(rel_path)
        if len(selected) >= max_files:
            break
    return selected[:max_files]


def repo_scan_semantic_candidates(repo_root: Path, *, max_files: int) -> list[Path]:
    return repo_scan_files(
        repo_root,
        max_files=max_files,
        suffixes={".py", ".ps1", ".md", ".json", ".yml", ".yaml", ".toml"},
    )


def existing_context_files(repo_root: Path, max_files: int = 240) -> list[str]:
    return repo_scan_context_files(repo_root, max_files=max_files)


def context_files_from_scan(scan_index: dict[str, Any], *, repo_root: Path, max_files: int) -> list[str]:
    priority_names = {"AGENTS.md", "README.md", "WORKFLOW.md"}
    by_path = {
        str(item.get("path") or ""): item
        for item in scan_index.get("files", [])
        if isinstance(item, dict)
    }
    selected: list[str] = []
    for rel_path in CANONICAL_CONTEXT_FILES:
        if rel_path in by_path and rel_path not in selected:
            selected.append(rel_path)
    markdown_paths = sorted(
        rel_path
        for rel_path, item in by_path.items()
        if str(item.get("suffix") or "").lower() == ".md"
    )
    for rel_path in markdown_paths:
        path = repo_root / rel_path
        if path.name in priority_names or rel_path.startswith("docs/"):
            if rel_path not in selected:
                selected.append(rel_path)
        if len(selected) >= max_files:
            break
    return selected[:max_files]


def semantic_candidates_from_scan(scan_index: dict[str, Any], *, repo_root: Path, max_files: int) -> list[Path]:
    suffixes = {".py", ".ps1", ".md", ".json", ".yml", ".yaml", ".toml"}
    paths = [
        repo_root / str(item.get("path") or "")
        for item in scan_index.get("files", [])
        if isinstance(item, dict) and str(item.get("suffix") or "").lower() in suffixes
    ]
    return paths[:max_files]
