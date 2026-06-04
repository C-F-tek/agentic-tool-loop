"""Repository path token normalization shared by planner/controller helpers."""
from __future__ import annotations

from typing import Any


def repo_rel_token(value: Any) -> str:
    """Normalize repo-relative path tokens without corrupting dot-directories.

    ``str.lstrip("./")`` removes all leading dots and slashes, so paths such as
    ``.github/workflows/x.yml`` become ``github/workflows/x.yml``. This helper
    removes only literal ``./`` prefixes and preserves real dot-directory names.
    """
    raw = str(value or "").strip().strip("\"'").replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw or "."
