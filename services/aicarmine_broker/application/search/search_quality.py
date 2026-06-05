"""Diagnostic quality assessment for search tool results."""

from __future__ import annotations

from typing import Any


SCHEMA = "search_quality.v1"


def _query_from(result: dict[str, Any], goal: str) -> str:
    query = str(result.get("query") or result.get("pattern") or "").strip()
    if query:
        return query
    words = [part.strip(".,;:!?()[]{}\"'") for part in str(goal or "").split()]
    useful = [word for word in words if len(word) > 3]
    return " ".join(useful[:4]) or str(goal or "").strip()[:80]


def _recommended_query(result: dict[str, Any], goal: str, reason: str) -> str:
    query = _query_from(result, goal)
    if not query:
        return ""
    if "truncated" in reason:
        return f"{query} with narrower path or higher limit"
    if "incomplete" in reason or "unreadable" in reason:
        return f"{query} with repo_search/repo_rg_search or narrower readable scope"
    if "zero" in reason:
        return f"{query} using alternate identifiers from the goal"
    return query


def assess_search_quality(result: dict[str, Any], *, goal: str = "") -> dict[str, Any]:
    """Classify a search result as complete, partial, weak or failed."""

    if not isinstance(result, dict):
        return {
            "schema": SCHEMA,
            "quality": "failed",
            "must_retry": True,
            "recommended_next_query": _recommended_query({}, goal, "invalid result"),
            "reason": "search result is not a dictionary",
            "diagnostic_only": True,
        }

    ok = bool(result.get("ok"))
    count = int(result.get("count") or len(result.get("matches") or result.get("items") or []))
    truncated = bool(result.get("truncated"))
    search_complete = result.get("search_complete")
    unreadable_files = int(result.get("unreadable_files") or 0)
    content_attempts = int(result.get("content_read_attempts") or 0)
    content_ok = int(result.get("content_read_ok") or 0)

    if not ok:
        reason = str(result.get("error") or "search failed")
        quality = "failed"
        must_retry = True
    elif truncated:
        reason = "search result truncated before complete scan"
        quality = "partial"
        must_retry = True
    elif unreadable_files > 0 or search_complete is False:
        reason = "search incomplete because unreadable files or incomplete scan were reported"
        quality = "partial"
        must_retry = True
    elif content_attempts and content_ok < content_attempts:
        reason = "search incomplete because not every content read succeeded"
        quality = "partial"
        must_retry = True
    elif count <= 0:
        reason = "zero search results"
        quality = "weak"
        must_retry = True
    else:
        reason = "search result complete with matches"
        quality = "complete"
        must_retry = False

    return {
        "schema": SCHEMA,
        "quality": quality,
        "must_retry": must_retry,
        "recommended_next_query": _recommended_query(result, goal, reason),
        "reason": reason,
        "result_tool": result.get("tool", ""),
        "count": count,
        "truncated": truncated,
        "search_complete": search_complete,
        "unreadable_files": unreadable_files,
        "diagnostic_only": True,
        "does_not_change_planner_gate": True,
    }
