"""Repository path token normalization shared by planner/controller helpers."""
from __future__ import annotations

from typing import Any

from .diagnostics import safe_text


def repo_path_token(value: Any, *, empty: str = "") -> str:
    """Normalize repo-relative path tokens without corrupting dot-directories.

    ``str.lstrip("./")`` removes all leading dots and slashes, so paths such as
    ``.github/workflows/x.yml`` become ``github/workflows/x.yml``. This helper
    removes only literal relative prefixes and preserves real dot-directory names.
    """
    raw = safe_text(value, limit=2000).strip().strip("\"'").replace("\\", "/")
    if not raw:
        return empty
    while raw.startswith("./"):
        raw = raw[2:]
    while raw.startswith("../"):
        raw = raw[3:]
    raw = raw.strip("/")
    while "//" in raw:
        raw = raw.replace("//", "/")
    return raw or empty


def repo_rel_token(value: Any) -> str:
    """Normalize repo-relative path tokens, returning ``"."`` for empty input."""
    return repo_path_token(value, empty=".")
