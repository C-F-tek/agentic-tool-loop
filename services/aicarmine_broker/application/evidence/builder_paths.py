"""Builder path logic extracted from builder.py.

Handles path collection, resolution, and matching utilities.
"""

from __future__ import annotations

from typing import Any, Callable


def collect_result_paths(
    value: Any,
    repo_rel_token: Callable[[Any], str],
    output: list[str] | None = None,
) -> list[str]:
    """Recursively collect file paths from a value."""
    if output is None:
        output = []
    if value in (None, "", [], {}):
        return output
    if isinstance(value, (list, tuple, set)):
        for item in value:
            collect_result_paths(item, repo_rel_token, output)
        return output
    if isinstance(value, dict):
        for key in ("path", "paths", "target", "targets", "target_file", "modified_paths"):
            if key in value:
                collect_result_paths(value.get(key), repo_rel_token, output)
        return output
    path = repo_rel_token(value)
    if path and path != "." and path not in output:
        output.append(path)
    return output


def tool_result_paths(
    result: dict[str, Any],
    repo_rel_token: Callable[[Any], str],
) -> list[str]:
    """Extract file paths from a tool result dict."""
    paths: list[str] = []
    for key in ("modified_paths", "paths", "path", "target", "targets", "target_file"):
        collect_result_paths(result.get(key), repo_rel_token, paths)
    compile_resolution = (
        result.get("compile_target_resolution")
        if isinstance(result.get("compile_target_resolution"), dict)
        else {}
    )
    collect_result_paths(compile_resolution.get("targets"), repo_rel_token, paths)
    return paths


def goal_mentions_repo_path(goal_low: str, path: str) -> bool:
    """Check if goal text mentions a repo path by name or stem."""
    normalized = str(path or "").replace("\\", "/").strip("/").lower()
    if not normalized:
        return False
    basename = normalized.rsplit("/", 1)[-1]
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    return bool(
        normalized in goal_low
        or (basename and basename in goal_low)
        or (stem and len(stem) >= 6 and stem in goal_low)
    )


def path_covers_target(path: str, target: str) -> bool:
    """Check if path covers target (same or ancestor directory)."""
    path = str(path or "").strip().strip("/")
    target = str(target or "").strip().strip("/")
    if not path or not target:
        return False
    return path == target or target.startswith(path + "/") or path.startswith(target + "/")


def validation_covers_modified_files(
    validation_paths: list[str],
    modified_files: list[str],
) -> bool:
    """Check if validation paths cover all modified files."""
    if not modified_files:
        return True
    if not validation_paths:
        return True
    return all(
        any(path_covers_target(vp, mf) for vp in validation_paths)
        for mf in modified_files
    )