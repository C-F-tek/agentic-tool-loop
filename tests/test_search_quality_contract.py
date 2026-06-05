from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.search.search_quality import assess_search_quality


def test_search_quality_marks_complete_search_with_matches() -> None:
    quality = assess_search_quality(
        {
            "ok": True,
            "tool": "terminal_search_files",
            "query": "needle",
            "count": 2,
            "search_complete": True,
            "truncated": False,
        },
        goal="find needle",
    )

    assert quality["schema"] == "search_quality.v1"
    assert quality["quality"] == "complete"
    assert quality["must_retry"] is False
    assert quality["diagnostic_only"] is True
    assert quality["does_not_change_planner_gate"] is True


def test_search_quality_marks_incomplete_terminal_search_partial() -> None:
    quality = assess_search_quality(
        {
            "ok": True,
            "tool": "terminal_search_files",
            "query": "needle",
            "count": 1,
            "search_complete": False,
            "unreadable_files": 1,
            "content_read_attempts": 2,
            "content_read_ok": 1,
        },
        goal="find needle",
    )

    assert quality["quality"] == "partial"
    assert quality["must_retry"] is True
    assert "repo_search" in quality["recommended_next_query"]


def test_search_quality_recommends_retry_on_truncated_result() -> None:
    quality = assess_search_quality(
        {
            "ok": True,
            "tool": "repo_rg_search",
            "query": "needle",
            "count": 50,
            "truncated": True,
        },
        goal="find needle",
    )

    assert quality["quality"] == "partial"
    assert quality["must_retry"] is True
    assert "higher limit" in quality["recommended_next_query"]


def test_search_quality_marks_zero_results_weak() -> None:
    quality = assess_search_quality(
        {
            "ok": True,
            "tool": "repo_search",
            "query": "missing_symbol",
            "count": 0,
            "search_complete": True,
        },
        goal="find missing symbol",
    )

    assert quality["quality"] == "weak"
    assert quality["must_retry"] is True
    assert "alternate identifiers" in quality["recommended_next_query"]


def test_search_quality_marks_failed_search_failed() -> None:
    quality = assess_search_quality(
        {
            "ok": False,
            "tool": "repo_rg_search",
            "error": "rg_not_found",
            "query": "needle",
        },
        goal="find needle",
    )

    assert quality["quality"] == "failed"
    assert quality["must_retry"] is True
    assert quality["reason"] == "rg_not_found"


def test_search_quality_report_is_json_serializable() -> None:
    quality = assess_search_quality({"ok": True, "query": "needle", "count": 1}, goal="find needle")

    json.dumps(quality, ensure_ascii=False)
