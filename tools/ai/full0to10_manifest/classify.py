"""Artifact role classification for Full0To10 manifests."""
from __future__ import annotations

import fnmatch

from .constants import ROLE_PATTERNS


def match_patterns(path: str, patterns: tuple[str, ...]) -> bool:
    name = path.replace("\\", "/").split("/")[-1]
    return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns)


def classify_records(records: list[dict[str, object]]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {role: [] for role in ROLE_PATTERNS}
    for record in records:
        path = str(record["path"])
        for role, patterns in ROLE_PATTERNS.items():
            if match_patterns(path, patterns):
                roles[role].append(path)
    return roles


def summarize_roles(roles: dict[str, list[str]]) -> dict[str, object]:
    missing = [role for role, paths in roles.items() if not paths]
    return {
        "passed": not missing,
        "missing_roles": missing,
        "role_counts": {role: len(paths) for role, paths in roles.items()},
        "roles": {role: paths[:40] for role, paths in roles.items()},
    }
