"""Agentic loop v2 progress/scope helpers extracted from planner.py.

These functions handle path aliasing (ai_carmine → ia_carmine), decision path
extraction, repo list row construction, and evidence contract enrichment.
"""
from __future__ import annotations

import json
from typing import Any


def _agentic_v2_alias_repo_path(path: Any) -> str:
    """Normalize repo-relative paths and map the user's ai_carmine alias."""
    from ..shared.path_tokens import repo_rel_token  # lazy import
    p = repo_rel_token(path)
    try:
        from ...config import LAB_REPO
        if (p == "ai_carmine" or p.startswith("ai_carmine/")) and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine" + p[len("ai_carmine"):]
    except Exception:
        pass
    return p


def _agentic_v2_goal_scope(goal: str, contract: dict[str, Any] | None = None) -> str:
    """Resolve the goal scope, applying ai_carmine → ia_carmine alias."""
    from ..shared.path_tokens import repo_rel_token
    from ..evidence.goal_classifier import semantic_goal_low  # lazy import
    contract = contract if isinstance(contract, dict) else {}
    scope = repo_rel_token(contract.get("resolved_goal_scope") or "")
    if scope and scope != ".":
        return scope
    low = semantic_goal_low(goal).replace("\\", "/")
    try:
        from ...config import LAB_REPO
        if "ai_carmine" in low and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine"
        if "ia_carmine" in low:
            return "ia_carmine"
    except Exception:
        if "ai_carmine" in low or "ia_carmine" in low:
            return "ia_carmine"
    return ""


# ---------------------------------------------------------------------------
# Flat decision table — replaces triangular if/elif chain
# ---------------------------------------------------------------------------

# Maps each tool to the argument keys that may contain file/directory paths.
# This is a single source of truth — no nested conditionals.
_TOOL_PATH_KEYS: dict[str, tuple[str, ...]] = {
    # Search/list tools — path + optional multi-path
    "repo_list_files": ("path", "paths"),
    "repo_tree": ("path", "paths"),
    "repo_search": ("path", "paths"),
    "repo_fd_files": ("path", "paths"),
    "repo_rg_search": ("path", "paths"),
    "repo_ast_grep_search": ("path", "paths"),
    "repo_ast_grep_dry_run": ("path", "paths"),
    "repo_tree_sitter_parse": ("path", "paths"),
    "repo_ctags_symbols": ("path", "paths"),
    "repo_semgrep_scan": ("path", "paths"),
    "repo_shellcheck": ("path", "paths"),
    "repo_validate": ("path", "paths"),
    "repo_ruff_check": ("path", "paths"),
    "repo_pyright_check": ("path", "paths"),
    "repo_pytest_run": ("path", "paths"),
    "repo_jq_query": ("path", "paths"),
    # Read tools — path + multi-path + file/item variants
    "repo_read": ("path", "paths", "file", "files", "item", "items"),
    # Write/edit tools — path variants
    "repo_write_file": ("path", "paths", "target_file", "target_path"),
    "repo_apply_patch": ("path", "paths", "target_file", "target_path"),
    "repo_propose_code_edit": ("path", "paths", "target_file", "target_path"),
}


def _agentic_v2_decision_paths(tool: str, args: dict[str, Any]) -> list[str]:
    """Extract file/directory paths from a tool call's arguments.

    Uses a flat decision table instead of triangular if/elif chains.
    """
    args = args if isinstance(args, dict) else {}
    paths: list[str] = []

    def add(value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for key in ("path", "file", "filename", "target_file", "target_path"):
                if value.get(key):
                    add(value.get(key))
            return
        p = _agentic_v2_alias_repo_path(value)
        if p and p not in paths:
            paths.append(p)

    # Flat lookup — O(1) instead of O(n) nested conditionals
    keys = _TOOL_PATH_KEYS.get(tool)
    if keys:
        for key in keys:
            add(args.get(key))
        # Default: use "." when only "path" exists but is empty
        if keys == ("path", "paths") and args.get("path") in (None, ""):
            add(".")
    return paths


def _agentic_v2_read_has_window(args: dict[str, Any]) -> bool:
    """Check if args contain window/line-range selectors."""
    args = args if isinstance(args, dict) else {}
    return any(k in args for k in (
        "start", "start_line", "end", "end_line", "offset", "limit",
        "line", "line_start", "line_count", "before", "after",
        "window", "chunk", "range",
    ))


def _agentic_v2_repo_list_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract repo_list_files rows with aliased paths from history."""
    from ..shared.history_ledger import history_tool_result  # lazy import
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        if result.get("tool") != "repo_list_files" or not result.get("ok"):
            continue
        paths: list[str] = []
        for key in ("paths", "paths_preview"):
            value = result.get(key)
            if isinstance(value, list):
                for raw in value:
                    if isinstance(raw, dict):
                        raw = raw.get("path")
                    p = _agentic_v2_alias_repo_path(raw)
                    if p and p not in paths:
                        paths.append(p)
        rows.append({
            "step": item.get("step"),
            "path": _agentic_v2_alias_repo_path(result.get("path") or "."),
            "total_matches": result.get("total_matches"),
            "limit": result.get("limit"),
            "truncated": result.get("truncated"),
            "paths": paths,
        })
    return rows


def _agentic_v2_successful_read_paths(history: list[dict[str, Any]]) -> list[str]:
    """Collect successful repo_read paths with ai_carmine alias applied."""
    from ..shared.history_ledger import history_tool_result  # lazy import
    from ...config import LAB_REPO
    from ..evidence.repo_history import successful_repo_read_paths
    paths: list[str] = []
    for p in successful_repo_read_paths(history if isinstance(history, list) else []):
        n = _agentic_v2_alias_repo_path(p)
        if n and n not in paths:
            paths.append(n)
    if paths:
        return paths
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        for value in (result.get("paths"), result.get("path")):
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                for raw in value:
                    if raw in (None, "", [], {}):
                        continue
                    n = _agentic_v2_alias_repo_path(raw)
                    if n and n not in paths:
                        paths.append(n)
            else:
                n = _agentic_v2_alias_repo_path(value)
                if n and n not in paths:
                    paths.append(n)
        for read_item in result.get("items") or []:
            if isinstance(read_item, dict) and read_item.get("ok") and read_item.get("path") not in (None, "", [], {}):
                n = _agentic_v2_alias_repo_path(read_item.get("path"))
                if n and n not in paths:
                    paths.append(n)
    return paths


def _agentic_v2_enrich_evidence_contract(contract: dict[str, Any], goal: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    """Enrich evidence contract with scope-aware path guidance."""
    from ...config import LAB_REPO
    from ..evidence.repo_path_policy import dynamic_read_candidate_paths, path_under_scope
    scope = _agentic_v2_goal_scope(goal, contract)
    list_rows = _agentic_v2_repo_list_rows(history)
    successful_reads = _agentic_v2_successful_read_paths(history)
    known_all: list[str] = []
    for row in list_rows:
        for p in row.get("paths") or []:
            if p not in known_all:
                known_all.append(p)
    in_scope: list[str] = []
    if scope:
        for p in known_all:
            if path_under_scope(p, scope) and p not in in_scope:
                in_scope.append(p)
    latest_in_scope = next((row for row in reversed(list_rows) if scope and path_under_scope(row.get("path") or ".", scope)), None)
    latest_any = list_rows[-1] if list_rows else None
    already_read = set(successful_reads)
    unread_in_scope = dynamic_read_candidate_paths(in_scope, read_ok=already_read, target_scope=scope)
    contract["resolved_goal_scope"] = scope or contract.get("resolved_goal_scope")
    contract["path_aliases"] = {"ai_carmine": "ia_carmine"} if scope == "ia_carmine" else contract.get("path_aliases", {})
    contract["repo_list_files_evidence"] = [
        {k: v for k, v in {
            "step": row.get("step"), "path": row.get("path"),
            "total_matches": row.get("total_matches"), "limit": row.get("limit"),
            "truncated": row.get("truncated"),
            "paths_preview": (row.get("paths") or [])[:20],
        }.items() if v not in (None, "", [], {})}
        for row in list_rows[-8:]
    ]
    if scope:
        scoped_latest_paths = list((latest_in_scope or {}).get("paths") or in_scope)
        if scoped_latest_paths:
            contract["known_paths_from_latest_repo_list_files"] = scoped_latest_paths[:80]
            contract["known_paths_total_in_latest_digest"] = len(scoped_latest_paths)
    contract["known_in_scope_paths_from_repo_list_files"] = in_scope[:80]
    contract["known_in_scope_paths_total"] = len(in_scope)
    contract["latest_in_scope_repo_list_path"] = latest_in_scope.get("path") if latest_in_scope else None
    contract["latest_repo_list_path"] = latest_any.get("path") if latest_any else None
    contract["successful_repo_read_paths"] = successful_reads
    contract["forbidden_repeated_repo_read_paths"] = successful_reads[:40]
    contract["unread_in_scope_candidate_paths"] = unread_in_scope[:40]
    guidance: list[str] = []
    if scope:
        guidance.append(f"Stay under resolved_goal_scope={scope}; do not call repo_list_files with path='.' or omitted path.")
    if successful_reads:
        guidance.append("Do not repo_read already successful paths: " + ", ".join(successful_reads[:8]))
    if unread_in_scope:
        guidance.append("Next valid progress can be repo_read one unread in-scope candidate or repo_list_files a new subdirectory under scope: " + ", ".join(unread_in_scope[:8]))
    elif latest_in_scope:
        guidance.append("If current in-scope evidence is enough, choose final and cite the read/list evidence already in history.")
    guidance.append("Controller validates only; planner must decide the next tool or final from these evidence-bound candidates.")
    contract["required_next_progress"] = " ".join(guidance)
    return contract


__all__ = [
    "_agentic_v2_alias_repo_path",
    "_agentic_v2_goal_scope",
    "_agentic_v2_decision_paths",
    "_agentic_v2_read_has_window",
    "_agentic_v2_repo_list_rows",
    "_agentic_v2_successful_read_paths",
    "_agentic_v2_enrich_evidence_contract",
]