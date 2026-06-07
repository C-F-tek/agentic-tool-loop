"""Controller preseed plan helpers for initial repository orientation."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..shared.path_tokens import repo_rel_token
from ..evidence.repo_path_policy import (
    low_signal_top_dir,
    repo_code_file,
    repo_doc_or_config,
    repo_existing_dir,
    repo_existing_file,
    repo_path_kind,
    top_dir,
)


SafeRelPath = Callable[[str], str]


def root_surface_entries(result: dict[str, Any], *, repo_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("entries", "entries_preview", "files", "files_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if not isinstance(value, list):
            continue
        for raw in value:
            if isinstance(raw, dict):
                path = repo_rel_token(raw.get("path") or "")
                kind = str(raw.get("kind") or "")
            else:
                path = repo_rel_token(raw)
                kind = ""
            if not path or path == ".":
                continue
            if not kind:
                kind = repo_path_kind(path, repo_root=repo_root)
            row = {"path": path, "kind": kind}
            if row not in entries:
                entries.append(row)
    return entries



def root_surface_file_paths(
    result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> list[str]:
    paths: list[str] = []
    for entry in root_surface_entries(result, repo_root=repo_root):
        path = str(entry.get("path") or "")
        if (
            entry.get("kind") == "file"
            and repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path)
            and path not in paths
        ):
            paths.append(path)
    return paths

def root_surface_dir_paths(
    result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> list[str]:
    paths: list[str] = []
    for entry in root_surface_entries(result, repo_root=repo_root):
        path = str(entry.get("path") or "")
        if (
            entry.get("kind") == "dir"
            and repo_existing_dir(path, repo_root=repo_root, safe_rel_path=safe_rel_path)
            and path not in paths
        ):
            paths.append(path)
    return paths


def initial_doc_sort_key(path: str, *, named_read_priority: Mapping[str, int]) -> tuple[int, int, str]:
    p = repo_rel_token(path)
    name = p.rsplit("/", 1)[-1].lower()
    priority = named_read_priority.get(name, len(named_read_priority))
    depth = p.count("/")
    return (priority, depth, p.lower())


def controller_initial_doc_preseed_plan(
    root_result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    named_read_priority: Mapping[str, int],
    initial_doc_name_priority: Mapping[str, int],
    scoped_concrete_read_target: int,
    multi_file_prompt_read_chars: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    files = root_surface_file_paths(root_result, repo_root=repo_root, safe_rel_path=safe_rel_path)
    docs = [path for path in files if repo_doc_or_config(path, repo_root=repo_root)]
    docs = sorted(docs, key=lambda path: initial_doc_sort_key(path, named_read_priority=named_read_priority))
    selected = docs[:scoped_concrete_read_target]

    skipped: list[dict[str, Any]] = []
    seen_names = {p.rsplit("/", 1)[-1] for p in files}
    for name in initial_doc_name_priority:
        if name not in seen_names:
            skipped.append({
                "candidate": name,
                "reason": "not_seen_in_root_surface",
                "stage": "initial_doc_read",
            })
    if docs and not selected:
        skipped.append({
            "candidate_count": len(docs),
            "reason": "doc_candidate_budget_exhausted",
            "stage": "initial_doc_read",
        })
    if not selected:
        return None, skipped

    return {
        "event": "controller_preseed_initial_docs",
        "result_event": "controller_preseed_initial_docs_result",
        "tool": "repo_read",
        "arguments": {"paths": selected, "max_chars": int(multi_file_prompt_read_chars)},
        "reason": "generic_repo_request_needs_existing_initial_docs_from_root_surface",
        "artifact_suffix": "initial_docs-repo_read",
        "dynamic_initial_orientation": True,
    }, skipped


def initial_area_sort_key(path: str) -> tuple[int, str]:
    top = top_dir(path)
    return (top.count("/"), top.lower())


def controller_initial_area_list_plans(
    root_result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dirs: list[str] = []
    for path in root_surface_dir_paths(root_result, repo_root=repo_root, safe_rel_path=safe_rel_path):
        top = top_dir(path)
        if (
            top
            and top not in dirs
            and not low_signal_top_dir(top)
            and repo_existing_dir(top, repo_root=repo_root, safe_rel_path=safe_rel_path)
        ):
            dirs.append(top)

    selected = sorted(dirs, key=initial_area_sort_key)[:3]
    skipped: list[dict[str, Any]] = []

    plans = [
        {
            "event": "controller_preseed_initial_area_list",
            "result_event": "controller_preseed_initial_area_list_result",
            "tool": "repo_list_files",
            "arguments": {"path": area, "limit": 120, "max_depth": 3},
            "reason": "generic_repo_request_needs_existing_useful_area_file_surface",
            "artifact_suffix": f"initial_area_{safe_rel_path(area).replace('/', '__')}-repo_list_files",
            "dynamic_initial_orientation": True,
        }
        for area in selected
    ]
    return plans, skipped


def list_result_file_paths(
    result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> list[str]:
    paths: list[str] = []
    for key in ("paths", "paths_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if isinstance(value, list):
            for raw in value:
                path = repo_rel_token(raw)
                if repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path) and path not in paths:
                    paths.append(path)
    for key in ("files", "files_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if isinstance(value, list):
            for raw in value:
                path = repo_rel_token(raw.get("path") if isinstance(raw, dict) else raw)
                if repo_existing_file(path, repo_root=repo_root, safe_rel_path=safe_rel_path) and path not in paths:
                    paths.append(path)
    return paths


def initial_area_file_sort_key(
    path: str,
    *,
    repo_root: Path,
    named_read_priority: Mapping[str, int],
) -> tuple[int, int, str]:
    p = repo_rel_token(path)
    name = p.rsplit("/", 1)[-1].lower()
    priority = named_read_priority.get(name, len(named_read_priority))
    if repo_doc_or_config(p, repo_root=repo_root):
        kind_rank = 0
    elif repo_code_file(p):
        kind_rank = 1
    else:
        kind_rank = 2
    return (priority, kind_rank, p.lower())


def controller_initial_area_read_plan(
    list_result: dict[str, Any],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
    named_read_priority: Mapping[str, int],
    single_file_prompt_read_chars: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    area = repo_rel_token(list_result.get("path") or "")
    candidates = [
        path for path in list_result_file_paths(list_result, repo_root=repo_root, safe_rel_path=safe_rel_path)
        if (repo_doc_or_config(path, repo_root=repo_root) or repo_code_file(path))
    ]
    candidates = sorted(
        candidates,
        key=lambda path: initial_area_file_sort_key(
            path,
            repo_root=repo_root,
            named_read_priority=named_read_priority,
        ),
    )
    if not candidates:
        return None, [{
            "candidate": area,
            "reason": "no_existing_doc_or_code_file_in_area_list_result",
            "stage": "initial_area_read",
        }]
    selected = candidates[0]
    return {
        "event": "controller_preseed_initial_area_read",
        "result_event": "controller_preseed_initial_area_read_result",
        "tool": "repo_read",
        "arguments": {"path": selected, "max_chars": int(single_file_prompt_read_chars)},
        "reason": "generic_repo_request_needs_concrete_file_read_inside_useful_area",
        "artifact_suffix": f"initial_area_{safe_rel_path(selected).replace('/', '__')}-repo_read",
        "dynamic_initial_orientation": True,
    }, []
