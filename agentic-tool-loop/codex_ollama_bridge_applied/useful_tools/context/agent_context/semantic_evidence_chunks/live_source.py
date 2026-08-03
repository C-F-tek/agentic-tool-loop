"""Current-source chunk helpers for semantic code context selection."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

SOURCE_SUFFIXES = (".py", ".ps1")


def repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def file_score(path: str, text: str, query_tokens: list[str], path_boosts: list[str]) -> int:
    haystack = f"{path}\n{text[:8000]}".lower()
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 1
        if token in path.lower():
            score += 4
    for boost in path_boosts:
        normalized = boost.lower().strip().replace("\\", "/")
        if normalized and normalized in path.lower():
            score += 10
    return score


def symbol_from_lines(lines: list[str]) -> str:
    for line in lines:
        match = re.match(r"\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if match:
            return match.group(1)
    return ""


def live_source_files(repo_root: Path, path_boosts: list[str]) -> list[Path]:
    roots: list[Path] = []
    for boost in path_boosts or ["ia_carmine", "Tools/npu", "Tools/workflow"]:
        candidate = repo_root / boost
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
        elif candidate.is_file() and candidate.suffix.lower() in SOURCE_SUFFIXES:
            roots.append(candidate)

    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if "__pycache__" in path.parts:
                continue
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                files.append(path)
    return sorted(dict.fromkeys(files), key=lambda item: repo_relative(repo_root, item).lower())


def build_live_source_chunks(
    repo_root: Path,
    query_tokens: list[str],
    path_boosts: list[str],
    *,
    max_files: int,
    max_chunk_chars: int,
) -> list[dict[str, Any]]:
    scored_files: list[tuple[int, Path, str]] = []
    for path in live_source_files(repo_root, path_boosts):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_path = repo_relative(repo_root, path)
        score = file_score(rel_path, text, query_tokens, path_boosts)
        if score <= 0:
            continue
        scored_files.append((score, path, text))

    scored_files.sort(key=lambda item: (-item[0], repo_relative(repo_root, item[1]).lower()))
    chunks: list[dict[str, Any]] = []
    for score, path, text in scored_files[:max_files]:
        lines = text.splitlines()
        rel_path = repo_relative(repo_root, path)
        for start, end, window_text in complete_line_windows(lines, max_chunk_chars):
            digest = hashlib.sha256(window_text.encode("utf-8", errors="replace")).hexdigest()
            window_lines = window_text.splitlines()
            chunks.append(
                {
                    "chunk_id": f"live_source::{rel_path}::{start}-{end}",
                    "path": rel_path,
                    "symbol": symbol_from_lines(window_lines),
                    "kind": "live_source_excerpt",
                    "line_start": start,
                    "line_end": end,
                    "domain": ["live_source_chunks"],
                    "risk": "medium",
                    "risk_signals": [],
                    "compatibility_notes": [
                        "generated from current source because semantic index artifact is unavailable"
                    ],
                    "dependencies": [],
                    "blender_api": [],
                    "summary_short": "Current source excerpt selected directly from repository files.",
                    "content_preview": window_text,
                    "do_not_change": False,
                    "sha256": digest,
                    "score": score,
                    "matched_terms": [],
                }
            )
    return chunks


def complete_line_windows(
    lines: list[str],
    max_chars: int,
    *,
    max_lines: int = 160,
) -> list[tuple[int, int, str]]:
    budget = max(1, int(max_chars or 1))
    windows: list[tuple[int, int, str]] = []
    current: list[str] = []
    start_line = 1
    total_chars = 0
    for line_no, line in enumerate(lines, start=1):
        line_chars = len(line) if not current else len(line) + 1
        if len(line) > budget:
            if current:
                windows.append((start_line, line_no - 1, "\n".join(current)))
                current = []
                total_chars = 0
            start_line = line_no + 1
            continue
        if current and (total_chars + line_chars > budget or len(current) >= max_lines):
            windows.append((start_line, line_no - 1, "\n".join(current)))
            current = [line]
            start_line = line_no
            total_chars = len(line)
            continue
        if not current:
            start_line = line_no
        current.append(line)
        total_chars += line_chars
    if current:
        windows.append((start_line, start_line + len(current) - 1, "\n".join(current)))
    return windows
