"""
path_utils.py
=============
Pure functions for path token normalization, validation, and scope checks.
No side-effects; all helpers return values without mutating anything.
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.shared.path_tokens import repo_path_token


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def is_concrete_repo_path(token: Any) -> bool:
    """Return True when *token* looks like a real relative file/dir path."""
    token = repo_path_token(token)
    if not token:
        return False
    lowered = token.lower()
    # Generic placeholder words that are not real paths
    if lowered in {"services", "tools", "cache", "cache_dir", "repo"}:
        return False
    if " " in token:
        return False
    if token in {".", ".."}:
        return False
    # Anything containing a separator or a dot (e.g. "foo/bar", "file.py")
    if "/" in token or "\\" in token:
        return True
    if token.count(".") >= 1:
        return True
    return False


def coalesce_repo_read_paths(values: Any) -> list[str]:
    """
    Flatten *values* (list/tuple) into a deduplicated list of concrete path
    tokens, preserving insertion order.
    """
    if isinstance(values, tuple):
        values = list(values)
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        token = repo_path_token(value)
        if not is_concrete_repo_path(token):
            continue
        if token not in out:
            out.append(token)
    return out


def collect_repo_paths(values: Any) -> set[str]:
    """
    Extract every path token reachable inside *values* (dict / list / scalar)
    and return them as a set.  Dict values and list items that are themselves
    dicts are inspected for "path", "source_path" and "repo_path" keys.
    """
    out: set[str] = set()
    if isinstance(values, dict):
        for item in values.values():
            token = repo_path_token(item)
            if token:
                out.add(token)
    elif isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                token = repo_path_token(
                    item.get("path") or item.get("source_path") or item.get("repo_path")
                )
            else:
                token = repo_path_token(item)
            if token:
                out.add(token)
    else:
        token = repo_path_token(values)
        if token:
            out.add(token)
    return out


# ---------------------------------------------------------------------------
# Prose / metric token detection
# ---------------------------------------------------------------------------

def is_prose_or_metric_token(value: Any) -> bool:
    """
    Return True when *value* looks like a prose description or a numeric
    metric rather than a real repo path (e.g. "8/2", "ridondanze/rischi").
    """
    token = repo_path_token(value)
    if not token:
        return True
    lowered = token.lower()
    if lowered in {
        "ridondanze/rischi",
        "docs/config",
        "planner/final-quality",
        "planner/controller rejection paths",
    }:
        return True
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return True
    if " " in token:
        return True
    return False


def is_concrete_search_query(value: Any) -> bool:
    """Return True when *value* is a useful, non-trivial search query string."""
    text = str(value or "").strip()
    if not text or len(text) > 260:
        return False
    lowered = text.lower()
    if lowered in {
        "docs/config",
        "ridondanze/rischi",
        "8/2",
        "8/8",
        "9/9",
        "planner/controller rejection paths",
    }:
        return False
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return False
    useful_tokens = [
        tok
        for tok in lowered.replace(",", " ").replace(";", " ").split()
        if len(tok) >= 3 and "/" not in tok and any(ch.isalpha() for ch in tok)
    ]
    if "/" in lowered and len(useful_tokens) < 2:
        return False
    return bool(useful_tokens)