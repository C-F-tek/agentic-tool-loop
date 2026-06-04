from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_result_digest import planner_last_result_digest  # noqa: E402


def test_planner_last_result_digest_preserves_code_product_payload() -> None:
    result = {
        "tool": "repo_propose_code_edit",
        "ok": True,
        "target_file": "a.py",
        "edit_kind": "unified_diff",
        "unified_diff": "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n",
        "source_writes_performed": False,
        "patch_application_performed": False,
        "manual_review_required": True,
    }

    digest = planner_last_result_digest(result)

    assert digest["tool"] == "repo_propose_code_edit"
    assert digest["target_file"] == "a.py"
    assert digest["unified_diff"].startswith("---")
    assert digest["source_writes_performed"] is False
    assert digest["manual_review_required"] is True


def test_planner_last_result_digest_bounds_normal_tool_items() -> None:
    result = {
        "tool": "repo_read",
        "ok": True,
        "items": [
            {
                "ok": True,
                "path": "a.py",
                "content": "x" * 900,
                "text": "t" * 900,
                "artifact": "reads/a.json",
            }
        ],
    }

    digest = planner_last_result_digest(result)

    assert digest["items"][0]["path"] == "a.py"
    assert len(digest["items"][0]["content_preview"]) == 700
    assert len(digest["items"][0]["text_preview"]) == 700


def test_planner_last_result_digest_preserves_prompt_context_window_metadata() -> None:
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": "prompt_context_window",
        "items": [{
            "document_id": "doc",
            "section": "evidence",
            "window_start": 0,
            "window_end": 10,
            "full_chars": 20,
            "window_chars": 10,
            "complete": False,
            "has_more_before": False,
            "has_more_after": True,
            "sha256": "full",
            "text": "window text",
        }],
    }

    digest = planner_last_result_digest(result)

    assert digest["mode"] == "prompt_context_window"
    assert digest["items"][0]["document_id"] == "doc"
    assert digest["items"][0]["text"] == "window text"
    assert digest["items"][0]["window_sha256"]
