"""Repository scanner for auto-refactor planning."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import CODE_SUFFIXES, MD_SUFFIXES, SKIP_DIR_NAMES


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def file_record(path: Path, repo_root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    trailing_ws = sum(1 for line in lines if line.rstrip() != line)
    return {
        "path": repo_relative(path, repo_root),
        "suffix": path.suffix.lower(),
        "line_count": len(lines),
        "size_bytes": path.stat().st_size,
        "trailing_whitespace_lines": trailing_ws,
        "final_newline": text.endswith("\n"),
        "lower_preview": text[:12000].lower(),
    }


def scan_repo(repo_root: Path, roots: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    suffixes = CODE_SUFFIXES + MD_SUFFIXES
    for root_name in roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes and not should_skip(path):
                records.append(file_record(path, repo_root))
    return sorted(records, key=lambda item: str(item["path"]))
