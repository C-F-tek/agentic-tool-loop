"""Diagnostic quality assessment forfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 search tool results."""

from __future__ import annotations

from typing import Any

from ..shared.diagnostics import diagnostic_row, safe_text


SCHEMA = "search_quality.v1"


def _query_from_with_diagnostics(result: dict[str, Any], goal: str) -> tuple[str, list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    query = safe_text(result.get("query") or result.get("pattern"), limit=300).strip()
    if query:
        return query, diagnostics
    goal_text = safe_text(goal, limit=700).strip()
    if not goal_text:
        diagnostics.append(diagnostic_row("search_query_source_empty", schema="search_query_diagnostic.v1"))
    if goal_text.startswith("<unstringifiable:"):
        diagnostics.append(diagnostic_row("search_goal_not_stringifiable", schema="search_query_diagnostic.v1"))
    words = [part.strip(".,;:!?()[]{}\"'") for part in goal_text.split()]
    useful = [word for word in words if len(word) > 3]
    return " ".join(useful[:4]) or goal_text[:80], diagnostics


def _query_from(result: dict[str, Any], goal: str) -> str:
    query, _diagnostics = _query_from_with_diagnostics(result, goal)
    return query


def _int_from(result: dict[str, Any], key: str, default: int, diagnostics: list[dict[str, Any]]) -> int:
    try:
        return int(result.get(key) or default)
    except (TypeError, ValueError) as exc:
        diagnostics.append(diagnostic_row(
            "search_quality_numeric_field_invalid",
            schema="search_quality_field_diagnostic.v1",
            exc=exc,
            field=key,
            received_preview=safe_text(result.get(key), limit=120),
        ))
        return default


def _result_sequence_len(result: dict[str, Any], diagnostics: list[dict[str, Any]]) -> int:
    value = result.get("matches") if result.get("matches") not in (None, "") else result.get("items")
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, list):
        return len(value)
    diagnostics.append(diagnostic_row(
        "search_quality_result_collection_invalid",
        schema="search_quality_field_diagnostic.v1",
        field="matches_or_items",
        received_type=type(value).__name__,
        received_preview=safe_text(value, limit=120),
    ))
    return 0


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
        query, query_diagnostics = _query_from_with_diagnostics({}, goal)
        return {
            "schema": SCHEMA,
            "quality": "failed",
            "must_retry": True,
            "recommended_next_query": query,
            "reason": "search result is not a dictionary",
            "query_diagnostics": query_diagnostics,
            "diagnostic_only": True,
        }

    query, query_diagnostics = _query_from_with_diagnostics(result, goal)
    diagnostics = list(query_diagnostics)
    ok = bool(result.get("ok"))
    count_default = _result_sequence_len(result, diagnostics)
    count = _int_from(result, "count", count_default, diagnostics)
    truncated = bool(result.get("truncated"))
    search_complete = result.get("search_complete")
    unreadable_files = _int_from(result, "unreadable_files", 0, diagnostics)
    content_attempts = _int_from(result, "content_read_attempts", 0, diagnostics)
    content_ok = _int_from(result, "content_read_ok", 0, diagnostics)

    if not ok:
        reason = safe_text(result.get("error") or "search failed", limit=700)
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
        "recommended_next_query": (
            f"{query} with narrower path or higher limit"
            if query and "truncated" in reason
            else f"{query} with repo_search/repo_rg_search or narrower readable scope"
            if query and ("incomplete" in reason or "unreadable" in reason)
            else f"{query} using alternate identifiers from the goal"
            if query and "zero" in reason
            else query
        ),
        "reason": reason,
        "result_tool": result.get("tool", ""),
        "count": count,
        "truncated": truncated,
        "search_complete": search_complete,
        "unreadable_files": unreadable_files,
        "query_diagnostics": diagnostics,
        "diagnostic_only": True,
        "does_not_change_planner_gate": True,
    }
