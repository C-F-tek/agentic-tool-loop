"""Single startup repository scan index for heap context reload."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from ia_carmine.context.heap_context_memory_reload.common import (
    REPO_SCAN_TEXT_SUFFIXES,
    read_json,
    repo_rel,
    write_json,
)
from ia_carmine.context.heap_context_memory_reload.scanner import is_repo_scan_excluded

STARTUP_SCAN_EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm"}


def _git_ls_files(repo_root: Path) -> tuple[list[str], str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return [], completed.stderr.decode("utf-8", errors="replace")[-1000:]
    text = completed.stdout.decode("utf-8", errors="replace")
    return [item.replace("\\", "/") for item in text.split("\x00") if item], ""


def _walk_files(repo_root: Path) -> list[str]:
    paths: list[str] = []
    for root, dirs, names in os.walk(repo_root):
        root_path = Path(root)
        dirs[:] = [
            name
            for name in dirs
            if not is_repo_scan_excluded(repo_rel(repo_root, root_path / name))
        ]
        for name in names:
            rel = repo_rel(repo_root, root_path / name)
            if not is_repo_scan_excluded(rel):
                paths.append(rel.replace("\\", "/"))
    return paths


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _partition(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    return normalized.split("/", 1)[0]


def _entry_signature(entry: dict[str, Any]) -> tuple[int, int]:
    return int(entry.get("size_bytes") or 0), int(entry.get("mtime_ns") or 0)


def build_startup_repo_scan_index(
    repo_root: Path,
    output_dir: Path,
    *,
    max_hash_size: int,
) -> dict[str, Any]:
    previous_path = repo_root / "output" / "ai_runtime_memory" / "startup_repo_scan_index.json"
    previous = read_json(previous_path)
    previous_entries = {
        str(item.get("path") or ""): item
        for item in previous.get("files", [])
        if isinstance(item, dict)
    }
    rel_paths, git_error = _git_ls_files(repo_root)
    discovery_mode = "git_ls_files"
    if not rel_paths:
        rel_paths = _walk_files(repo_root)
        discovery_mode = "os_walk_scan"
    warnings = [f"git ls-files unavailable; used os_walk_scan: {git_error}"] if git_error else []
    files: list[dict[str, Any]] = []
    changed: list[str] = []
    unchanged = 0
    hashed = 0
    skipped = 0
    seen: set[str] = set()
    for rel in sorted(rel_paths):
        normalized = rel.replace("\\", "/")
        if normalized in seen or is_repo_scan_excluded(normalized):
            continue
        seen.add(normalized)
        path = repo_root / normalized
        try:
            stat = path.stat()
        except OSError:
            skipped += 1
            continue
        if not path.is_file():
            skipped += 1
            continue
        suffix = path.suffix.lower()
        if suffix in STARTUP_SCAN_EXCLUDED_SUFFIXES:
            skipped += 1
            continue
        previous_entry = previous_entries.get(normalized)
        unchanged_by_stat = bool(previous_entry) and _entry_signature(previous_entry) == (
            int(stat.st_size),
            int(stat.st_mtime_ns),
        )
        content_hash = str(previous_entry.get("content_hash") or "") if previous_entry else ""
        hash_status = "unchanged_reused" if unchanged_by_stat and content_hash else ""
        if unchanged_by_stat:
            unchanged += 1
        else:
            changed.append(normalized)
            if suffix in REPO_SCAN_TEXT_SUFFIXES and int(stat.st_size) <= max(1, int(max_hash_size)):
                try:
                    content_hash = _file_hash(path)
                    hash_status = "changed_hashed"
                    hashed += 1
                except OSError as exc:
                    hash_status = f"hash_failed:{type(exc).__name__}"
                    warnings.append(f"{normalized}: {hash_status}")
            else:
                hash_status = "changed_unhashed_policy"
        files.append(
            {
                "path": normalized,
                "size_bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "suffix": suffix,
                "top_level_partition": _partition(normalized),
                "text_candidate": suffix in REPO_SCAN_TEXT_SUFFIXES,
                "content_hash": content_hash,
                "content_hash_status": hash_status,
                "delta_status": "unchanged_ref_only" if unchanged_by_stat else "changed_or_new",
            }
        )
    current_paths = {str(item.get("path") or "") for item in files}
    deleted = sorted(set(previous_entries) - current_paths)
    partitions: dict[str, dict[str, int]] = {}
    for item in files:
        partition = str(item.get("top_level_partition") or "")
        bucket = partitions.setdefault(partition, {"file_count": 0, "changed_count": 0})
        bucket["file_count"] += 1
        if item.get("delta_status") == "changed_or_new":
            bucket["changed_count"] += 1
    index = {
        "schema_version": 1,
        "kind": "heap_startup_repo_scan_index",
        "passed": True,
        "repo_root": repo_root.as_posix(),
        "discovery_mode": discovery_mode,
        "file_count": len(files),
        "changed_file_count": len(changed),
        "unchanged_ref_only_count": unchanged,
        "deleted_file_count": len(deleted),
        "hashed_changed_file_count": hashed,
        "skipped_file_count": skipped,
        "changed_files": changed[:500],
        "deleted_files": deleted[:500],
        "partitions": partitions,
        "warnings": warnings[:80],
        "hash_policy": "hash changed text candidates up to max_hash_size; reuse previous hash for unchanged stat matches",
        "max_hash_size": max(1, int(max_hash_size)),
        "files": files,
    }
    output_path = output_dir / "startup_repo_scan_index.json"
    write_json(output_path, index)
    previous_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(previous_path, index)
    return index


def scan_entries_by_path(scan_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("path") or ""): item
        for item in scan_index.get("files", [])
        if isinstance(item, dict)
    }


def scan_digest_for_paths(entries: list[dict[str, Any]]) -> str:
    payload = [
        {
            "path": item.get("path"),
            "size_bytes": item.get("size_bytes"),
            "mtime_ns": item.get("mtime_ns"),
            "content_hash": item.get("content_hash"),
        }
        for item in sorted(entries, key=lambda value: str(value.get("path") or ""))
    ]
    raw = repr(payload).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()
