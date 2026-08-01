from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import os
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import repo_rel, safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.deterministic_common import bounded_int_arg, deterministic_input_error
from aicarmine_broker.tools.git_surface import git_candidate_files


def repo_tree(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    try:
        max_files = bounded_int_arg(args, "max_files", default=200, minimum=1, maximum=2000)
        max_depth = bounded_int_arg(args, "max_depth", default=3, minimum=0, maximum=100)
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return deterministic_input_error("repo_tree", exc)
    excluded_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        "output",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return {
            "ok": False,
            "tool": "repo_tree",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {"ok": False, "tool": "repo_tree", "path": rel, "error": "path_not_found"}

    entries: list[dict[str, Any]] = []
    entries_total = 0
    source = "filesystem_walk"
    if base.is_file():
        git_files = git_candidate_files(LAB_REPO, base)
        if git_files == []:
            entries_total = 0
            source = "git_ls_files_exclude_standard"
        else:
            entries.append({"path": repo_rel(base, LAB_REPO), "kind": "file", "size_bytes": base.stat().st_size})
            entries_total = 1
            source = "git_ls_files_exclude_standard" if git_files is not None else source
    else:
        git_files = git_candidate_files(LAB_REPO, base)
        if git_files is not None:
            source = "git_ls_files_exclude_standard"
            base_rel = "." if rel == "." else rel.rstrip("/")
            rows: dict[str, dict[str, Any]] = {}
            for fp in git_files:
                file_rel = repo_rel(fp, LAB_REPO)
                try:
                    local_parts = fp.relative_to(base).parts
                except ValueError:
                    continue
                parent_parts = local_parts[:-1]
                for depth, _ in enumerate(parent_parts, start=1):
                    if depth > max_depth:
                        continue
                    dir_path = "/".join(parent_parts[:depth])
                    repo_path = dir_path if base_rel == "." else f"{base_rel}/{dir_path}"
                    rows.setdefault(repo_path, {"path": repo_path, "kind": "dir"})
                if len(parent_parts) <= max_depth:
                    rows[file_rel] = {"path": file_rel, "kind": "file", "size_bytes": fp.stat().st_size}
            all_entries = sorted(rows.values(), key=lambda item: (str(item.get("path") or "").lower(), str(item.get("kind") or "")))
            entries_total = len(all_entries)
            entries = all_entries[:max_files]
        else:
            base_depth = len(base.relative_to(LAB_REPO).parts)
            all_entries: list[dict[str, Any]] = []
            for current, dirs, files in os.walk(base):
                cp = Path(current)
                depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
                dirs[:] = [d for d in dirs if d not in excluded_dirs]
                if depth > max_depth:
                    dirs[:] = []
                    continue
                for dn in dirs:
                    all_entries.append({"path": repo_rel(cp / dn, LAB_REPO), "kind": "dir"})
                for fn in files:
                    p = cp / fn
                    all_entries.append({"path": repo_rel(p, LAB_REPO), "kind": "file", "size_bytes": p.stat().st_size})
            entries_total = len(all_entries)
            entries = all_entries[:max_files]

    payload = {
        "ok": True,
        "tool": "repo_tree",
        "path": rel,
        "count": len(entries),
        "entries_total": entries_total,
        "entries": entries,
        "truncated": entries_total > len(entries),
        "source": source,
        "gitignore_respected": source == "git_ls_files_exclude_standard",
        "coverage_status": "truncated" if entries_total > len(entries) else "complete",
        "suggested_next_actions": (
            [
                {
                    "tool": "repo_semantic_search",
                    "argument_hints": {
                        "path": rel,
                        "query": "derive_from_current_goal",
                    },
                    "reason": "directory_or_file_list_truncated_use_goal_specific_query",
                    "requires_goal_specific_query": True,
                    "not_runnable_without_query": True,
                }
            ]
            if entries_total > len(entries)
            else []
        ),
    }
    artifact = root / "tool-results" / f"{now()}-repo_tree.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
