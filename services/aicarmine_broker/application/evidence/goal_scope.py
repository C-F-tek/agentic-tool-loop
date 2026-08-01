"""Goal path/scope extraction helperfrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

s."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .goal_classifier import semantic_goal_low, semantic_goal_text
from ..shared.path_tokens import repo_rel_token


SafeRelPath = Callable[[str], str]

_GOAL_PATH_PATTERN = re.compile(
    r"([A-Za-z0-9_./\\-]+?\.(?:py|ps1|md|json|toml|yml|yaml|txt))"
)
_KNOWN_DOTFILE_NAMES = (
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".editorconfig",
    ".env",
    ".env.example",
    ".prettierrc",
    ".eslintrc",
    ".npmrc",
    ".python-version",
)


def _existing_repo_file(candidate: str, *, repo_root: Path, safe_rel_path: SafeRelPath) -> str:
    normalized = repo_rel_token(candidate)
    if not normalized:
        return ""
    try:
        rel = safe_rel_path(normalized)
        full = (repo_root / rel).resolve(strict=False)
        full.relative_to(repo_root)
    except Exception:
        return ""
    if full.exists() and full.is_file():
        return rel
    return ""


def _goal_path_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for dotfile in _KNOWN_DOTFILE_NAMES:
        if re.search(rf"(?<![A-Za-z0-9_/\\.-]){re.escape(dotfile)}(?![A-Za-z0-9_/\\.-])", text):
            candidates.append(dotfile)
    candidates.extend(match.group(1) for match in _GOAL_PATH_PATTERN.finditer(text))
    return candidates


def extract_existing_goal_path(
    goal: str,
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> str:
    semantic = semantic_goal_text(goal)
    raw = str(goal or "")
    for text in (semantic, raw):
        for candidate in _goal_path_candidates(text):
            rel = _existing_repo_file(candidate, repo_root=repo_root, safe_rel_path=safe_rel_path)
            if rel:
                return rel
    return ""


def extract_existing_goal_paths(
    goal: str,
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> list[str]:
    out: list[str] = []
    for text in (semantic_goal_text(goal), str(goal or "")):
        for candidate in _goal_path_candidates(text):
            rel = _existing_repo_file(candidate, repo_root=repo_root, safe_rel_path=safe_rel_path)
            if rel and rel not in out:
                out.append(rel)
    return out


def requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    text = semantic_goal_low(goal)
    patterns = (
        r"(?:first|primi|prime|top|limit|limite)\D{0,24}(\d{1,4})",
        r"(\d{1,4})\D{0,24}(?:file|files|py|python)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return max(1, min(int(match.group(1)), 1000))
            except Exception:
                pass
    return default


def goal_requested_repo_scope(
    goal: str,
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> str:
    """Resolve an explicit repo subdirectory mentioned by the user."""
    low = semantic_goal_low(goal).replace("\\", "/")
    candidates: list[str] = []
    for match in re.findall(r"(?:dentro|in|under|sotto)\s+([A-Za-z0-9_./-]+)", low):
        candidates.append(repo_rel_token(match))
    if "ai_carmine" in low:
        candidates.append("ai_carmine")
    if "ia_carmine" in low:
        candidates.append("ia_carmine")
    for raw in candidates:
        if not raw:
            continue
        normalized = repo_rel_token(raw)
        if normalized == "ai_carmine" and not (repo_root / normalized).exists() and (repo_root / "ia_carmine").is_dir():
            return "ia_carmine"
        try:
            rel = safe_rel_path(normalized)
            full = (repo_root / rel).resolve(strict=False)
            full.relative_to(repo_root)
        except Exception:
            continue
        if full.exists() and full.is_dir():
            return rel
    return ""
