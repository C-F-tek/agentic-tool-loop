"""Git-aware repository file discovery for RAG ingest."""

from __future__ import annotations

import os
import subprocess
from typing import Any
from dataclasses import dataclass
from pathlib import Path

from .common import (
    DEFAULT_MAX_FILE_SIZE,
    EXCLUDED_PARTS,
    EXCLUDED_SUFFIXES,
    JSON_MAX_FILE_SIZE,
    TEXT_SUFFIXES,
    repo_rel,
)


@dataclass(frozen=True)
class RepoFile:
    path: Path
    rel_path: str
    size_bytes: int
    suffix: str


def _has_excluded_part(rel_path: str) -> bool:
    parts = {part for part in rel_path.replace("\\", "/").split("/") if part}
    return bool(parts & EXCLUDED_PARTS)


def _candidate_paths_from_git(repo_root: Path) -> tuple[list[str], str]:
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return [], completed.stderr.decode("utf-8", errors="replace")[-1000:]
    text = completed.stdout.decode("utf-8", errors="replace")
    return [item for item in text.split("\x00") if item], ""


def _candidate_paths_from_walk(repo_root: Path) -> list[str]:
    paths: list[str] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [item for item in dirs if item not in EXCLUDED_PARTS]
        root_path = Path(root)
        for name in files:
            rel = repo_rel(repo_root, root_path / name)
            if not _has_excluded_part(rel):
                paths.append(rel)
    return paths


def is_text_candidate(rel_path: str, path: Path, max_file_size: int) -> tuple[bool, str]:
    normalized = rel_path.replace("\\", "/")
    suffix = path.suffix.lower()
    if _has_excluded_part(normalized):
        return False, "excluded_path_part"
    if suffix in EXCLUDED_SUFFIXES:
        return False, "excluded_suffix"
    if suffix not in TEXT_SUFFIXES:
        return False, "unsupported_suffix"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"stat_failed:{type(exc).__name__}"
    if size <= 0:
        return False, "empty_file"
    if size > max_file_size:
        return False, "max_file_size_exceeded"
    if suffix == ".json" and size > JSON_MAX_FILE_SIZE:
        return False, "json_policy_large_file_skipped"
    return True, ""


def list_repo_text_files(
    repo_root: Path, *, max_file_size: int = DEFAULT_MAX_FILE_SIZE
) -> tuple[list[RepoFile], list[dict[str, str]], list[str]]:
    rel_paths, git_error = _candidate_paths_from_git(repo_root)
    warnings: list[str] = []
    if git_error:
        warnings.append(f"git ls-files unavailable; using os_walk_scan: {git_error}")
    if not rel_paths:
        rel_paths = _candidate_paths_from_walk(repo_root)
    files: list[RepoFile] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for rel in sorted(rel_paths):
        normalized = rel.replace("\\", "/")
        if normalized in seen:
            continue
        seen.add(normalized)
        path = (repo_root / normalized).resolve(strict=False)
        ok, reason = is_text_candidate(normalized, path, max_file_size)
        if not ok:
            skipped.append({"path": normalized, "reason": reason})
            continue
        files.append(
            RepoFile(
                path=path,
                rel_path=normalized,
                size_bytes=path.stat().st_size,
                suffix=path.suffix.lower(),
            )
        )
    return files, skipped, warnings


def list_repo_text_files_from_scan(
    repo_root: Path,
    scan_index: dict[str, Any],
    *,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> tuple[list[RepoFile], list[dict[str, str]], list[str]]:
    files: list[RepoFile] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for item in scan_index.get("files", []):
        if not isinstance(item, dict):
            continue
        normalized = str(item.get("path") or "").replace("\\", "/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        path = (repo_root / normalized).resolve(strict=False)
        ok, reason = is_text_candidate(normalized, path, max_file_size)
        if not ok:
            skipped.append({"path": normalized, "reason": reason})
            continue
        files.append(
            RepoFile(
                path=path,
                rel_path=normalized,
                size_bytes=int(item.get("size_bytes") or path.stat().st_size),
                suffix=str(item.get("suffix") or path.suffix).lower(),
            )
        )
    return sorted(files, key=lambda value: value.rel_path), skipped, warnings
