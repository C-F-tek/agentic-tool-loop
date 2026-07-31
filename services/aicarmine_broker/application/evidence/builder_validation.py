"""Builder validation logic extracted from builder.py.

Handles post-write validation contract computation.
"""

from __future__ import annotations
from typing import Any, Callable

POST_WRITE_VALIDATION_TOOLS = frozenset({
    "repo_validate",
    "repo_ruff_check",
    "repo_pyright_check",
    "repo_pytest_run",
})
POST_WRITE_TOOL_NAMES = frozenset({"repo_apply_patch", "repo_write_file"})


def path_covers_target(path: str, target: str) -> bool:
    """Check if path covers target (same or ancestor)."""
    path = str(path or "").strip().strip("/")
    target = str(target or "").strip().strip("/")
    if not path or not target:
        return False
    return path == target or target.startswith(path + "/") or path.startswith(target + "/")


def validation_covers_modified_files(validation_paths: list[str], modified_files: list[str]) -> bool:
    """Check if validation paths cover all modified files."""
    if not modified_files:
        return True
    if not validation_paths:
        return True
    return all(
        any(path_covers_target(path, target) for path in validation_paths)
        for target in modified_files
    )


def post_write_validation_candidates(
    modified_files: list[str],
    validation_failed: bool = False,
) -> list[dict[str, Any]]:
    """Build candidate next actions for post-write validation."""
    paths = modified_files[:8]
    candidates: list[dict[str, Any]] = []
    if validation_failed and paths:
        candidates.append({
            "tool": "repo_read",
            "arguments": {
                "paths": paths,
                "max_chars": 50000,
                "max_paths": len(paths),
            },
            "reason": "post_write_validation_failed_read_modified_files",
            "source": "post_write_validation_contract",
        })
    validate_args: dict[str, Any] = {"timeout_seconds": 300}
    if paths:
        validate_args["paths"] = paths
    candidates.append({
        "tool": "repo_validate",
        "arguments": validate_args,
        "reason": "post_write_validation_required",
        "source": "post_write_validation_contract",
    })
    python_paths = [path for path in paths if path.endswith(".py")]
    if python_paths:
        candidates.append({
            "tool": "repo_ruff_check",
            "arguments": {"paths": python_paths, "timeout_seconds": 180},
            "reason": "post_write_python_validation_candidate",
            "source": "post_write_validation_contract",
        })
    return candidates


def compute_post_write_validation_contract(
    history: list[dict[str, Any]],
    repo_rel_token: Callable[[Any], str],
    history_result_fn: Any = None,
) -> dict[str, Any]:
    """Compute post-write validation contract from history."""
    if history_result_fn is None:
        def history_result_fn(row: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(row, dict):
                return {}
            result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            if result:
                return result
            return row if row.get("tool") else {}

    def collect_result_paths(
        value: Any,
        output: list[str],
        repo_rel_token_fn: Callable[[Any], str],
    ) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                collect_result_paths(item, output, repo_rel_token_fn)
            return
        if isinstance(value, dict):
            for key in ("path", "paths", "target", "targets", "target_file", "modified_paths"):
                if key in value:
                    collect_result_paths(value.get(key), output, repo_rel_token_fn)
            return
        path = repo_rel_token_fn(value)
        if path and path != "." and path not in output:
            output.append(path)

    def tool_result_paths(result: dict[str, Any]) -> list[str]:
        paths: list[str] = []
        for key in ("modified_paths", "paths", "path", "target", "targets", "target_file"):
            collect_result_paths(result.get(key), paths, repo_rel_token)
        compile_resolution = (
            result.get("compile_target_resolution")
            if isinstance(result.get("compile_target_resolution"), dict)
            else {}
        )
        collect_result_paths(compile_resolution.get("targets"), paths, repo_rel_token)
        return paths

    write_events: list[dict[str, Any]] = []
    for index, row in enumerate(history if isinstance(history, list) else []):
        result = history_result_fn(row)
        tool = str(result.get("tool") or "")
        if tool not in POST_WRITE_TOOL_NAMES or result.get("ok") is not True:
            continue
        if tool == "repo_apply_patch" and result.get("changed") is False:
            continue
        paths = tool_result_paths(result)
        write_events.append({
            "index": index,
            "tool": tool,
            "paths": paths,
            "changed": result.get("changed"),
        })

    modified_files: list[str] = []
    for event in write_events:
        for path in event.get("paths") or []:
            if path not in modified_files:
                modified_files.append(path)

    latest_write_index = max((int(event["index"]) for event in write_events), default=-1)
    validation_events: list[dict[str, Any]] = []
    for index, row in enumerate(history if isinstance(history, list) else []):
        if index <= latest_write_index:
            continue
        result = history_result_fn(row)
        tool = str(result.get("tool") or "")
        if tool not in POST_WRITE_VALIDATION_TOOLS:
            continue
        paths = tool_result_paths(result)
        covers_modified_files = validation_covers_modified_files(paths, modified_files)
        validation_events.append({
            "index": index,
            "tool": tool,
            "ok": result.get("ok") is True,
            "paths": paths,
            "covers_modified_files": covers_modified_files,
            "returncode": result.get("returncode"),
            "error": result.get("error"),
        })

    latest_covering_validation = next(
        (event for event in reversed(validation_events) if event.get("covers_modified_files")),
        {},
    )
    validation_done = bool(latest_covering_validation and latest_covering_validation.get("ok") is True)
    validation_failed = bool(latest_covering_validation and latest_covering_validation.get("ok") is not True)
    status = (
        "not_required"
        if not write_events else
        "passed"
        if validation_done else
        "failed"
        if validation_failed else
        "pending"
    )
    return {
        "schema": "post_write_validation_contract.v1",
        "required": bool(write_events),
        "status": status,
        "validation_done": validation_done,
        "validation_failed": validation_failed,
        "required_after_tools": sorted(POST_WRITE_TOOL_NAMES),
        "accepted_validation_tools": sorted(POST_WRITE_VALIDATION_TOOLS),
        "modified_files": modified_files[:32],
        "latest_write_index": latest_write_index if latest_write_index >= 0 else None,
        "write_events": write_events[-8:],
        "validation_events_after_latest_write": validation_events[-8:],
        "latest_validation": latest_covering_validation or None,
        "candidate_next_actions": post_write_validation_candidates(
            modified_files,
            validation_failed=validation_failed,
        ) if write_events and not validation_done else [],
    }