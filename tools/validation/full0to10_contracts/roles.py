"""Required role validation for Full0To10 bundles."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .constants import REQUIRED_BUNDLE_ROLES


@dataclass(frozen=True)
class RoleCheck:
    role: str
    passed: bool
    matches: list[str]
    patterns: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "passed": self.passed,
            "matches": self.matches,
            "patterns": self.patterns,
        }


def match_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    return any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns)


def check_required_roles(paths: list[str]) -> list[RoleCheck]:
    checks: list[RoleCheck] = []
    for role, patterns in REQUIRED_BUNDLE_ROLES:
        matches = [path for path in paths if match_any(path, patterns)]
        checks.append(RoleCheck(role=role, passed=bool(matches), matches=matches[:30], patterns=list(patterns)))
    return checks
