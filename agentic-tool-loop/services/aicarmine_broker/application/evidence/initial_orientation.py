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
        "preplanner_rag": {},
        "ranked_preplanner_paths": [],
        "selected_paths": [],
        "anchor_paths": [],
    }

    docs_read: list[str] = []
    files_read: list[str] = []
    areas_listed: list[str] = []

    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        raw_decision = row.get("decision")
        decision: dict[str, Any] = raw_decision if isinstance(raw_decision, dict) else {}
        raw_result = row.get("tool_result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
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

        preplanner_rag = result.get("preplanner_rag")
        if isinstance(preplanner_rag, dict) and preplanner_rag:
            surface["preplanner_rag"] = preplanner_rag
            selected_paths = preplanner_rag.get("selected_paths")
            if isinstance(selected_paths, list):
                for raw_path in selected_paths:
                    path = repo_rel_token(raw_path)
                    if path and path not in surface["selected_paths"]:
                        surface["selected_paths"].append(path)
            anchor_paths = preplanner_rag.get("anchor_paths")
            if isinstance(anchor_paths, list):
                for raw_path in anchor_paths:
                    path = repo_rel_token(raw_path)
                    if path and path not in surface["anchor_paths"]:
                        surface["anchor_paths"].append(path)
        ranked_paths = result.get("ranked_preplanner_paths")
        if isinstance(ranked_paths, list):
            for raw_path in ranked_paths:
                path = repo_rel_token(raw_path)
                if path and path not in surface["ranked_preplanner_paths"]:
                    surface["ranked_preplanner_paths"].append(path)
        selected_paths = result.get("selected_paths")
        if isinstance(selected_paths, list):
            for raw_path in selected_paths:
                path = repo_rel_token(raw_path)
                if path and path not in surface["selected_paths"]:
                    surface["selected_paths"].append(path)

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
    ranked_preplanner_paths = {
        repo_rel_token(path)
        for path in surface["ranked_preplanner_paths"]
        if repo_rel_token(path)
    }
    area_scoped_useful_reads = [
        path for path in files_read
        if any(path_under_scope(path, area) and not low_signal_top_dir(area) for area in areas_listed)
    ]
    ranked_useful_reads = [
        path for path in files_read
        if path in ranked_preplanner_paths
        and not repo_doc_or_config(path)
        and not low_signal_top_dir(path)
    ]
    concrete_useful_reads: list[str] = []
    for path in [*area_scoped_useful_reads, *ranked_useful_reads]:
        if path not in concrete_useful_reads:
            concrete_useful_reads.append(path)
    surface["ranked_preplanner_useful_file_read_count"] = len(ranked_useful_reads)
    surface["concrete_useful_file_read_count"] = len(concrete_useful_reads)
    return surface
