from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.required_working_set import (  # noqa: E402
    latest_code_product_for_prompt,
    repo_read_items_for_prompt,
    required_working_set_for_prompt,
)


def _history_tool_result(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}


def _window_text(text: str, *, max_chars: int) -> dict[str, Any]:
    return {
        "text": text[:max_chars],
        "full_chars": len(text),
        "window_chars": max_chars,
        "complete": len(text) <= max_chars,
        "has_more_after": len(text) > max_chars,
    }


def _store_window(root: Path, **kwargs) -> dict[str, Any]:
    text = str(kwargs.get("text") or "")
    max_chars = int(kwargs.get("max_chars") or 100)
    return {
        "document_id": f"doc:{kwargs.get('section')}",
        "section": kwargs.get("section"),
        "text": text[:max_chars],
        "window_start": 0,
        "window_end": min(len(text), max_chars),
        "full_chars": len(text),
        "window_chars": max_chars,
        "complete": len(text) <= max_chars,
        "has_more_before": False,
        "has_more_after": len(text) > max_chars,
        "metadata": kwargs.get("metadata") or {},
        "root": str(root),
    }


def test_repo_read_items_for_prompt_builds_real_content_window(tmp_path: Path) -> None:
    history = [{
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "items": [{"ok": True, "path": "a.py", "line_count": 1, "truncated": False}],
        }
    }]

    items = repo_read_items_for_prompt(
        history,
        {"a.py"},
        job_root=tmp_path,
        goal="goal",
        window_chars=10,
        compact_mode=False,
        history_tool_result=_history_tool_result,
        repo_rel_token=lambda value: str(value),
        repo_read_item_full_content=lambda _raw: ("print('x')", {"source": "repo_file_rehydrated_for_prompt_window"}),
        store_prompt_text_window=_store_window,
        window_text=_window_text,
    )

    assert items[0]["path"] == "a.py"
    assert items[0]["full_context_reconstructed"] is True
    assert items[0]["content_window"]["text"] == "print('x')"


def test_latest_code_product_for_prompt_windows_large_diff(tmp_path: Path) -> None:
    history = [{
        "tool_result": {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "target_file": "a.py",
            "edit_kind": "unified_diff",
            "unified_diff": "--- a\n+++ b\n@@\n" + ("x" * 1000),
        }
    }]

    product = latest_code_product_for_prompt(
        history,
        job_root=tmp_path,
        goal="diff",
        window_chars=20,
        compact_mode=True,
        store_prompt_text_window=_store_window,
        text_hash=lambda text: f"hash:{len(text)}",
    )

    assert product["target_file"] == "a.py"
    assert "unified_diff_window" in product
    assert product["planner_can_request_more"]["arguments"]["offset"] == 800
    assert product["unified_diff_sha256"].startswith("hash:")


def test_required_working_set_for_prompt_collects_targets_and_limits(tmp_path: Path) -> None:
    history = [{
        "tool_result": {
            "tool": "repo_read",
            "ok": True,
            "items": [{"ok": True, "path": "a.py", "line_count": 1, "truncated": True}],
        }
    }]

    required = required_working_set_for_prompt(
        "edit a.py",
        history,
        {"resolved_goal_file": "a.py", "code_product_contract": {"candidate_target_file": "b.py"}},
        job_root=tmp_path,
        window_chars=20,
        compact_mode=False,
        repo_rel_token=lambda value: str(value),
        goal_target_file=lambda _goal: "a.py",
        latest_code_product_build_state=lambda _history, target: {"target_file": target},
        history_tool_result=_history_tool_result,
        repo_read_item_full_content=lambda _raw: ("preview only", {"source": "content_preview_only"}),
        store_prompt_text_window=_store_window,
        window_text=_window_text,
        text_hash=lambda text: str(len(text)),
    )

    assert required["schema"] == "planner_required_working_set.v1"
    assert required["target_paths"] == ["a.py", "b.py"]
    assert required["repo_reads"][0]["path"] == "a.py"
    assert required["limits"] == [
        {"path": "a.py", "kind": "repo_read_not_full_content", "content_source": "content_preview_only"},
        {"path": "a.py", "kind": "repo_read_content_preview_only"},
    ]
    assert required["errors"] == []
