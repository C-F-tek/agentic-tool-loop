#!/usr/bin/env python3
"""Artifact manifest, discovery and bounded content helpers for evidence bundles."""
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from Tools.ai.github_evidence_bundle_io import (
    CONTENT_EXTENSION_ALLOWLIST,
    MAX_ARTIFACT_PREVIEW_CHARS,
    line_count,
    normalize_manifest_path,
    raw_artifact_content_allowed,
    read_json,
    read_text,
    resolve_repo_path,
    sha256_file,
)

DEFAULT_CHUNK_LINES = 200
DEFAULT_RECURSIVE_MAX_FILES = 120
DEFAULT_RECURSIVE_EXCLUDE_GLOBS: tuple[str, ...] = (
    "output/ai_pipeline/*checkpoints*",
    "output/ai_context_packs/*",
    "indexAI/code_chunks/*",
    "indexAI/project_code_chunks/*",
    "renders/*",
    "*.db",
    "*.sqlite",
    "*.sqlite-wal",
    "*.sqlite-shm",
    "*full_analysis*",
    "*analysis_full*",
)


def base_artifact_entry(path: Path, repo_root: Path, role: str) -> dict[str, Any]:
    """Return common artifact metadata fields."""
    return {
        "path": normalize_manifest_path(path, repo_root),
        "exists": path.exists(),
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        "sha256": sha256_file(path),
        "role": role,
    }


def path_matches_any_glob(rel_path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Return whether a normalized repository path matches one deny glob."""
    normalized = rel_path.replace("\\", "/")
    return any(fnmatch(normalized, pattern.replace("\\", "/")) for pattern in patterns)


def text_line_chunks(rel_path: str, text: str, *, max_lines: int) -> list[dict[str, Any]]:
    """Build pointer-linked chunk metadata for a large text artifact."""
    if max_lines <= 0:
        return []
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return []
    chunks: list[dict[str, Any]] = []
    chunk_count = (len(lines) + max_lines - 1) // max_lines
    for index in range(chunk_count):
        start = index * max_lines + 1
        end = min((index + 1) * max_lines, len(lines))
        chunk_id = f"{rel_path}#L{start}-L{end}"
        previous_id = None
        next_id = None
        if index > 0:
            prev_start = (index - 1) * max_lines + 1
            prev_end = min(index * max_lines, len(lines))
            previous_id = f"{rel_path}#L{prev_start}-L{prev_end}"
        if index + 1 < chunk_count:
            next_start = (index + 1) * max_lines + 1
            next_end = min((index + 2) * max_lines, len(lines))
            next_id = f"{rel_path}#L{next_start}-L{next_end}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "path": rel_path,
                "line_start": start,
                "line_end": end,
                "previous_chunk_id": previous_id,
                "next_chunk_id": next_id,
                "has_previous": previous_id is not None,
                "has_next": next_id is not None,
            }
        )
    return chunks


def chunk_index_entry(path: Path, repo_root: Path, *, max_lines: int) -> dict[str, Any] | None:
    """Return one chunk index entry for JSON/Markdown files above the line threshold."""
    if max_lines <= 0 or path.suffix.lower() not in {".json", ".md"}:
        return None
    rel = normalize_manifest_path(path, repo_root)
    text, error = read_text(path)
    if error:
        return {"path": rel, "exists": path.exists(), "read_error": error, "chunks": []}
    chunks = text_line_chunks(rel, text, max_lines=max_lines)
    if not chunks:
        return None
    return {
        "path": rel,
        "suffix": path.suffix.lower(),
        "line_count": line_count(text),
        "chunk_size_lines": max_lines,
        "chunk_count": len(chunks),
        "first_chunk_id": chunks[0]["chunk_id"],
        "last_chunk_id": chunks[-1]["chunk_id"],
        "chunks": chunks,
    }


def build_artifact_chunk_index(
    repo_root: Path,
    paths: list[Path],
    *,
    max_lines_per_chunk: int,
) -> list[dict[str, Any]]:
    """Build deduplicated chunk index entries for large JSON/Markdown files."""
    if max_lines_per_chunk <= 0:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        key = path.resolve().as_posix() if path.exists() else path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        if not path.exists() or not path.is_file():
            continue
        entry = chunk_index_entry(path, repo_root, max_lines=max_lines_per_chunk)
        if entry:
            out.append(entry)
    return out


def summarize_artifact(path: Path, repo_root: Path) -> dict[str, Any]:
    """Return a compact manifest entry for a local artifact/report path."""
    item = base_artifact_entry(path, repo_root, "local_artifact_reference")
    item["content_included"] = False

    if not path.exists() or not path.is_file():
        return item

    rel = str(item["path"])
    if path.suffix.lower() in CONTENT_EXTENSION_ALLOWLIST and raw_artifact_content_allowed(rel):
        text, error = read_text(path)
        if error:
            item["read_error"] = error
            return item
        item["preview"] = text[:MAX_ARTIFACT_PREVIEW_CHARS]
        item["preview_chars"] = min(len(text), MAX_ARTIFACT_PREVIEW_CHARS)
        item["line_count"] = line_count(text)
        item["content_included"] = bool(item["preview"])

    return item


def build_included_artifact(
    path: Path,
    repo_root: Path,
    *,
    max_chars: int,
    role: str,
    max_lines_per_chunk: int = 0,
) -> dict[str, Any]:
    """Return bounded artifact content and pointer metadata for large files."""
    item = base_artifact_entry(path, repo_root, role)
    item["content_included"] = False
    item["content_truncated"] = False
    item["chunked_content"] = False
    if not path.exists() or not path.is_file():
        return item
    rel = str(item["path"])
    if path.suffix.lower() not in CONTENT_EXTENSION_ALLOWLIST:
        item["skip_reason"] = "suffix_not_text_allowlisted"
        return item
    if not raw_artifact_content_allowed(rel):
        item["skip_reason"] = "raw_artifact_content_denied_by_policy"
        return item
    text, error = read_text(path)
    if error:
        item["read_error"] = error
        return item
    item["line_count"] = line_count(text)
    item["raw_chars"] = len(text)
    item["included_chars"] = min(len(text), max_chars)
    item["content"] = text[:max_chars]
    item["content_truncated"] = len(text) > max_chars
    item["content_included"] = True
    chunk_entry = chunk_index_entry(path, repo_root, max_lines=max_lines_per_chunk)
    if chunk_entry:
        item["chunked_content"] = True
        item["chunk_size_lines"] = chunk_entry["chunk_size_lines"]
        item["chunk_count"] = chunk_entry["chunk_count"]
        item["first_chunk_id"] = chunk_entry["first_chunk_id"]
        item["last_chunk_id"] = chunk_entry["last_chunk_id"]
        item["chunk_pointers"] = chunk_entry["chunks"]
    return item


def append_declared_artifacts(discovered: list[Path], repo_root: Path, data: dict[str, Any]) -> None:
    """Append report-declared related artifacts to a discovered path list."""
    for key in ("markdown_output", "markdown_report", "csv_written"):
        value = data.get(key)
        if isinstance(value, str):
            discovered.append(resolve_repo_path(repo_root, value))
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    for value in inputs.values():
        if isinstance(value, str) and value:
            path = resolve_repo_path(repo_root, value)
            if path.exists() and path.is_file():
                discovered.append(path)


def discover_related_artifacts(repo_root: Path, report_paths: list[Path]) -> list[Path]:
    """Discover useful sibling/declared artifacts for bounded bundle inclusion."""
    discovered: list[Path] = []
    for report in report_paths:
        if report.suffix.lower() == ".json":
            sibling_md = report.with_suffix(".md")
            if sibling_md.exists():
                discovered.append(sibling_md)
        data = read_json(report)
        if data:
            append_declared_artifacts(discovered, repo_root, data)
    unique: dict[str, Path] = {}
    for path in discovered:
        key = path.resolve().as_posix() if path.exists() else path.as_posix()
        unique[key] = path
    return sorted(unique.values(), key=lambda item: normalize_manifest_path(item, repo_root).lower())


def discover_recursive_artifacts(
    repo_root: Path,
    roots: list[str],
    *,
    suffixes: tuple[str, ...],
    stamp: str | None,
    include_unstamped: bool,
    max_files: int,
    exclude_globs: tuple[str, ...] | list[str] = DEFAULT_RECURSIVE_EXCLUDE_GLOBS,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Discover stamped JSON/Markdown artifacts under safe bounded roots."""
    discovered: list[Path] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()
    normalized_suffixes = tuple(item.lower() for item in suffixes)
    for root in roots:
        root_path = resolve_repo_path(repo_root, root)
        root_rel = normalize_manifest_path(root_path, repo_root)
        if not root_path.exists():
            skipped.append({"path": root_rel, "reason": "recursive root missing"})
            continue
        if not root_path.is_dir():
            skipped.append({"path": root_rel, "reason": "recursive root is not a directory"})
            continue
        for path in sorted(root_path.rglob("*"), key=lambda item: normalize_manifest_path(item, repo_root).lower()):
            if len(discovered) >= max_files:
                skipped.append({"path": root_rel, "reason": f"recursive max files reached: {max_files}"})
                return discovered, skipped
            if not path.is_file() or path.suffix.lower() not in normalized_suffixes:
                continue
            rel = normalize_manifest_path(path, repo_root)
            if path_matches_any_glob(rel, exclude_globs):
                skipped.append({"path": rel, "reason": "excluded by recursive guardrail"})
                continue
            if not raw_artifact_content_allowed(rel):
                skipped.append({"path": rel, "reason": "content denied by shared evidence-bundle policy"})
                continue
            if stamp and not include_unstamped and stamp not in rel:
                skipped.append({"path": rel, "reason": "stamp not present in file name/path"})
                continue
            key = path.resolve().as_posix()
            if key in seen:
                continue
            discovered.append(path)
            seen.add(key)
    return discovered, skipped


def build_included_artifacts(
    repo_root: Path,
    report_paths: list[Path],
    artifact_paths: list[Path],
    *,
    auto_include_related: bool,
    max_chars: int,
    max_artifacts: int,
    recursive_artifact_paths: list[Path] | None = None,
    max_lines_per_chunk: int = 0,
) -> list[dict[str, Any]]:
    """Build deduplicated bounded included-artifact entries."""
    auto_artifacts = discover_related_artifacts(repo_root, report_paths) if auto_include_related else []
    included_candidates: list[tuple[Path, str]] = [(path, "explicit_artifact") for path in artifact_paths]
    included_candidates.extend((path, "recursive_default_artifact") for path in (recursive_artifact_paths or []))
    included_candidates.extend((path, "auto_related_artifact") for path in auto_artifacts)
    deduped: dict[str, tuple[Path, str]] = {}
    for path, role in included_candidates:
        key = path.resolve().as_posix() if path.exists() else path.as_posix()
        deduped[key] = (path, role)
    return [
        build_included_artifact(
            path,
            repo_root,
            max_chars=max_chars,
            role=role,
            max_lines_per_chunk=max_lines_per_chunk,
        )
        for path, role in list(deduped.values())[:max_artifacts]
    ]
