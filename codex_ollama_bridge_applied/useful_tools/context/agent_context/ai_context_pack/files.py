"""Context file entry construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    context_unavailable_reason,
    normalize_repo_path,
    path_escapes_repo,
    path_policy_error,
    physical_line_count,
    resolve_repo_path,
    safe_read_split_markdown,
    safe_read_text,
    sha256_text,
)

def build_file_entry(
    *,
    repo_root: Path,
    item: dict[str, Any],
    required: bool,
    remaining_chars: int,
    max_file_chars: int,
) -> tuple[dict[str, Any], int]:
    raw_path = normalize_repo_path(item.get("path"))
    role = str(item.get("role") or "context")
    policy_error = path_policy_error(raw_path)
    full_path = resolve_repo_path(repo_root, raw_path) if raw_path else repo_root
    entry: dict[str, Any] = {
        "path": raw_path,
        "role": role,
        "required": required,
        "exists": False,
        "included": False,
        "policy_ok": policy_error is None,
        "policy_error": policy_error or "",
        "size_bytes": 0,
        "line_count": 0,
        "sha256": "",
        "chars": 0,
        "included_chars": 0,
        "truncated": False,
        "read_error": "",
        "content": "",
    }
    if policy_error:
        return entry, remaining_chars
    if path_escapes_repo(repo_root, full_path):
        entry["policy_ok"] = False
        entry["policy_error"] = "path escapes repository root"
        return entry, remaining_chars
    if not full_path.exists():
        entry["read_error"] = "file is missing"
        return entry, remaining_chars

    if full_path.is_file():
        text, read_error = safe_read_text(full_path)
        entry["size_bytes"] = full_path.stat().st_size
    else:
        text, read_error, split_size = safe_read_split_markdown(full_path)
        entry["size_bytes"] = split_size

    if not full_path.is_file() and text is None:
        entry["read_error"] = read_error or "path is not a file"
        return entry, remaining_chars

    entry["exists"] = True
    if read_error or text is None:
        entry["read_error"] = read_error or "unknown read error"
        return entry, remaining_chars

    entry["line_count"] = physical_line_count(text)
    entry["sha256"] = sha256_text(text)
    entry["chars"] = len(text)
    budget = max(0, min(remaining_chars, max_file_chars))
    if budget <= 0:
        entry["read_error"] = "context character budget exhausted"
        return entry, remaining_chars
    included = text[:budget]
    entry["included"] = True
    entry["included_chars"] = len(included)
    entry["truncated"] = len(included) < len(text)
    entry["content"] = included
    return entry, remaining_chars - len(included)

def profile_items(profile: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    required = [
        (item, True) for item in profile.get("required_files", []) if isinstance(item, dict)
    ]
    optional = [
        (item, False) for item in profile.get("optional_files", []) if isinstance(item, dict)
    ]
    return [*required, *optional]
