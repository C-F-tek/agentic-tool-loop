from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO, parse_bool
from aicarmine_broker.infrastructure.filesystem_repo import repo_rel, safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.deterministic_common import bounded_int_arg, deterministic_input_error
from aicarmine_broker.tools.git_surface import git_candidate_files


_EXCLUDE_DIRS_DEFAULT = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        "output",
        "indexAI",
    }
)


def repo_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    suffix = str(args.get("suffix") or args.get("extension") or "").strip().lower()
    try:
        limit = bounded_int_arg(args, ("limit", "max_files"), default=20, minimum=1, maximum=2000)
        max_depth = bounded_int_arg(args, "max_depth", default=50, minimum=0, maximum=1000)
    except Exception as exc:
        return deterministic_input_error("repo_list_files", exc)
    core = parse_bool(args.get("core", False), False)

    if core and path in {"", "."}:
        path = "ia_carmine"
    if core and not suffix:
        suffix = ".py"

    user_exclude_dirs = set(str(d) for d in (args.get("exclude_dirs") or []))
    fallback_exclude_dirs = set(user_exclude_dirs)
    fallback_exclude_dirs |= _EXCLUDE_DIRS_DEFAULT

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_list_files",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {"ok": False, "tool": "repo_list_files", "path": rel, "error": "path_not_found"}

    def _accept(fp: Path) -> bool:
        return not suffix or fp.suffix.lower() == suffix

    files: list[dict[str, Any]] = []
    source = "filesystem_walk"
    if base.is_file():
        git_files = git_candidate_files(LAB_REPO, base)
        if git_files == []:
            source = "git_ls_files_exclude_standard"
        elif _accept(base):
            files.append({"path": repo_rel(base, LAB_REPO), "size_bytes": base.stat().st_size})
            if git_files is not None:
                source = "git_ls_files_exclude_standard"
    else:
        git_files = git_candidate_files(LAB_REPO, base)
        if git_files is not None:
            source = "git_ls_files_exclude_standard"
            for fp in git_files:
                try:
                    local_parts = fp.relative_to(base).parts
                except ValueError:
                    continue
                if len(local_parts[:-1]) > max_depth:
                    continue
                if any(part in user_exclude_dirs for part in local_parts[:-1]):
                    continue
                if _accept(fp):
                    files.append({"path": repo_rel(fp, LAB_REPO), "size_bytes": fp.stat().st_size})
        else:
            base_depth = len(base.relative_to(LAB_REPO).parts)
            for current, dirs, filenames in os.walk(base):
                cp = Path(current)
                depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
                dirs[:] = [d for d in dirs if d not in fallback_exclude_dirs]
                if depth > max_depth:
                    dirs[:] = []
                    continue
                for fn in filenames:
                    fp = cp / fn
                    if _accept(fp):
                        files.append({"path": repo_rel(fp, LAB_REPO), "size_bytes": fp.stat().st_size})

    files = sorted(files, key=lambda x: str(x.get("path") or "").lower())
    selected = files[:limit]
    payload = {
        "ok": True,
        "tool": "repo_list_files",
        "path": rel if path not in {"", "."} else ".",
        "suffix": suffix,
        "core": core,
        "limit": limit,
        "count": len(selected),
        "total_matches": len(files),
        "files": selected,
        "paths": [str(x["path"]) for x in selected],
        "truncated": len(files) > limit,
        "source": source,
        "gitignore_respected": source == "git_ls_files_exclude_standard",
        "coverage_status": "truncated" if len(files) > limit else "complete",
        "suggested_next_tool_calls": (
            [
                {
                    "tool": "repo_semantic_search",
                    "arguments": {"query": "find entry point", "path": rel},
                    "reason": "narrow_down_large_file_list",
                }
            ]
            if len(files) > limit
            else []
        ),
    }
    artifact = root / "tool-results" / f"{now()}-repo_list_files.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
