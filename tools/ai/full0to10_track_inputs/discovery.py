"""Discovery helpers for Full0To10 track inputs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import INPUT_ROLES, ROLE_PATTERNS, SEARCH_ROOTS
from .paths import existing_search_roots, is_excluded, repo_relative


def score_candidate(path: Path, role: str, track_name: str) -> int:
    name = path.name.lower()
    stem = path.stem.lower()
    score = 0
    for pattern in ROLE_PATTERNS[role]:
        if name == pattern:
            score += 80
        elif name.endswith(pattern):
            score += 55
        elif pattern.replace(".json", "") in stem:
            score += 35
    if track_name and track_name.lower() in path.as_posix().lower():
        score += 20
    if "output" in {part.lower() for part in path.parts}:
        score += 5
    return score


def scan_json_candidates(repo_root: Path, track_name: str, max_candidates: int) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {role: [] for role in INPUT_ROLES}
    roots = existing_search_roots(repo_root, SEARCH_ROOTS)
    for root in roots:
        for path in root.rglob("*.json"):
            if is_excluded(path):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size <= 0:
                continue
            for role in INPUT_ROLES:
                score = score_candidate(path, role, track_name)
                if score > 0:
                    results[role].append(
                        {
                            "path": repo_relative(path, repo_root),
                            "score": score,
                            "size_bytes": size,
                            "role": role,
                        }
                    )

    for role in INPUT_ROLES:
        results[role] = sorted(results[role], key=lambda item: (-int(item["score"]), item["path"]))[:max_candidates]
    return results


def selected_inputs(candidates: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any] | None]:
    return {
        role: values[0] if values else None
        for role, values in candidates.items()
    }
