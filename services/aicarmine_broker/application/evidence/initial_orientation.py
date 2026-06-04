"""Initial read-only orientation surface for broad repository jobs."""

from __future__ import annotations

from typing import Any, Callable


PathNormalizer = Callable[[Any], str]
PathPredicate = Callable[[str], bool]
ScopePredicate = Callable[[str, str], bool]


def initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
    *,
    repo_rel_token: PathNormalizer,
    repo_doc_or_config: PathPredicate,
    low_signal_top_dir: PathPredicate,
    path_under_scope: ScopePredicate,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "schema": "agentic_loop_initial_orientation_surface.v1",
        "controller_preseed_read_only": True,
        "planner_decides_after_preseed": True,
        "root_tree": {},
        "docs_read": [],
        "areas_listed": [],
        "files_read": [],
        "skipped_candidates": list(skipped or []),
        "preseed_steps": [],
    }

    docs_read: list[str] = []
    files_read: list[str] = []
    areas_listed: list[str] = []

    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
        if not result.get("controller_preseed") and decision.get("action") != "controller_preseed":
            continue
        tool = str(result.get("tool") or decision.get("tool") or "")
        reason = str(result.get("preseed_reason") or decision.get("reason") or "")
        step_info = {
            "step": row.get("step"),
            "preseed_index": result.get("preseed_index") or row.get("preseed_index"),
            "tool": tool,
            "ok": result.get("ok"),
            "reason": reason,
            "artifact": result.get("artifact"),
        }
        surface["preseed_steps"].append({k: v for k, v in step_info.items() if v not in (None, "", [], {})})

        if tool == "repo_tree" and str(result.get("path") or ".") in {"", "."}:
            surface["root_tree"] = {
                "ok": result.get("ok"),
                "path": result.get("path") or ".",
                "count": result.get("entries_total") or result.get("count"),
                "truncated": result.get("truncated"),
                "artifact": result.get("artifact"),
            }
        elif tool == "repo_list_files":
            path = repo_rel_token(result.get("path") or "")
            if path and path not in areas_listed:
                areas_listed.append(path)
        elif tool == "repo_read":
            for item in result.get("items") or []:
                if not isinstance(item, dict) or not item.get("ok") or not item.get("path"):
                    continue
                path = repo_rel_token(item.get("path"))
                if repo_doc_or_config(path) and path not in docs_read:
                    docs_read.append(path)
                if path not in files_read:
                    files_read.append(path)

    surface["docs_read"] = docs_read[:80]
    surface["areas_listed"] = areas_listed[:40]
    surface["files_read"] = files_read[:120]
    surface["doc_read_count"] = len(docs_read)
    surface["area_list_count"] = len(areas_listed)
    surface["file_read_count"] = len(files_read)
    surface["useful_area_list_count"] = len([
        path for path in areas_listed
        if path not in {"", "."} and not low_signal_top_dir(path)
    ])
    surface["concrete_useful_file_read_count"] = len([
        path for path in files_read
        if any(path_under_scope(path, area) and not low_signal_top_dir(area) for area in areas_listed)
    ])
    return surface
