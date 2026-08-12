"""Path, text and worker helpers for repository consistency maps."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from Tools.ai.repository_consistency_map.constants import (
    EXCLUDE_DIRS,
    GENERATED_EVIDENCE_CHUNK_RE,
    TEXT_EXTENSIONS,
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def elapsed_seconds(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def normalize_ref(value: str) -> str:
    normalized = value.strip().strip("'\"<>()[]{}.,:;").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def is_generated_evidence_chunk_path(rel_posix: str) -> bool:
    """Return true for generated semantic evidence chunks excluded from findings."""
    normalized = rel_posix.replace("\\", "/").lower().strip("/")
    return bool(GENERATED_EVIDENCE_CHUNK_RE.search(normalized))


def should_skip(path: Path, repo_root: Path) -> bool:
    try:
        rel_path = path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except ValueError:
        return True
    rel_parts = rel_path.parts
    rel_posix = rel_path.as_posix()
    return any(part in EXCLUDE_DIRS for part in rel_parts) or is_generated_evidence_chunk_path(rel_posix)


def iter_files(repo_root: Path, extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path, repo_root):
            continue
        if path.suffix.lower() in extensions:
            files.append(path)
    return sorted(files, key=lambda item: repo_rel(item, repo_root))


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace"), None
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def snippet_for_line(text: str, line_no: int, *, max_chars: int) -> str:
    lines = text.splitlines()
    if line_no < 1 or line_no > len(lines):
        return ""
    snippet = lines[line_no - 1].strip()
    if len(snippet) > max_chars:
        return snippet[: max_chars - 3] + "..."
    return snippet


def build_existing_path_index(repo_root: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for path in iter_files(repo_root, TEXT_EXTENSIONS | {".json", ".csv"}):
        rel = repo_rel(path, repo_root)
        index[rel.lower()] = rel
        index[path.name.lower()] = rel
    return index


def resolve_repo_reference(repo_root: Path, source: str, raw_ref: str, path_index: dict[str, str]) -> tuple[str, bool, str]:
    ref = normalize_ref(raw_ref)
    if not ref or ref.startswith(("http://", "https://", "mailto:")):
        return ref, True, "external_or_empty"
    direct = (repo_root / ref).resolve(strict=False)
    if direct.exists():
        return repo_rel(direct, repo_root), True, "direct"
    source_parent = (repo_root / source).parent
    relative = (source_parent / ref).resolve(strict=False)
    if relative.exists():
        return repo_rel(relative, repo_root), True, "relative_to_source"
    indexed = path_index.get(ref.lower()) or path_index.get(Path(ref).name.lower())
    if indexed:
        return indexed, True, "basename_index"
    return ref, False, "missing"


def bounded_worker_count(requested: int, workload_count: int) -> int:
    """Return a conservative worker count for repository scans."""
    if workload_count <= 1:
        return 1
    if requested <= 0:
        requested = 8
    return max(1, min(requested, workload_count))
