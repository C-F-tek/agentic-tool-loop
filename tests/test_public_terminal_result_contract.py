from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_terminal_result import (  # noqa: E402
    public_terminal_history_ledger,
    public_terminal_result_for_30b,
)


def _repo_read_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return str(item.get("content") or item.get("full_content") or ""), {"source": "test"}


def test_public_terminal_history_ledger_repo_read_uses_content_metadata_not_local_paths() -> None:
    ledger = public_terminal_history_ledger(
        [{
            "step": 1,
            "decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": r"C:\Users\carmi\AI\a.py"}},
            "tool_result": {
                "tool": "repo_read",
                "ok": True,
                "path": r"C:\Users\carmi\AI\a.py",
                "items": [{"ok": True, "path": "a.py", "line_count": 1, "truncated": False, "content": "print(1)\n"}],
            },
        }],
        repo_read_item_full_content=_repo_read_full_content,
    )

    row = ledger[0]
    assert row["tool"] == "repo_read"
    assert row["arguments"]["path"] == "[local_path_omitted]"
    assert row["path"] == "[local_path_omitted]"
    assert row["items"][0]["content_chars"] == 9
    assert row["items"][0]["path"] == "a.py"
    assert "content_sha256" in row["items"][0]


def test_public_terminal_history_ledger_code_product_preserves_complete_diff() -> None:
    diff = "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n"
    ledger = public_terminal_history_ledger(
        [{
            "step": 2,
            "decision": {"action": "tool", "tool": "repo_propose_code_edit"},
            "tool_result": {
                "tool": "repo_propose_code_edit",
                "ok": True,
                "kind": "code_edit_proposal",
                "target_file": "a.py",
                "edit_kind": "unified_diff",
                "rationale": "real refactor",
                "unified_diff": diff,
                "manual_review_required": True,
            },
        }],
        repo_read_item_full_content=_repo_read_full_content,
    )

    assert ledger[0]["unified_diff"] == diff
    assert ledger[0]["manual_review_required"] is True


def test_public_terminal_history_ledger_prompt_context_window_keeps_tracking_window() -> None:
    ledger = public_terminal_history_ledger(
        [{
            "step": 3,
            "decision": {"action": "tool", "tool": "planner_scratchpad_read"},
            "tool_result": {
                "tool": "planner_scratchpad_read",
                "ok": True,
                "mode": "prompt_context_window",
                "items": [{
                    "document_id": "internal-doc",
                    "text": "visible window",
                    "window_start": 10,
                    "window_end": 24,
                    "full_chars": 100,
                    "window_chars": 14,
                    "complete": False,
                    "has_more_before": True,
                    "has_more_after": True,
                    "sha256": "a",
                    "window_sha256": "b",
                }],
            },
        }],
        repo_read_item_full_content=_repo_read_full_content,
    )

    assert ledger[0]["mode"] == "prompt_context_window"
    assert ledger[0]["items"][0]["text"] == "visible window"
    assert ledger[0]["items"][0]["window_end"] == 24
    assert "document_id" not in ledger[0]["items"][0]


def test_public_terminal_result_for_30b_normalizes_history_and_strips_raw_validation() -> None:
    result = public_terminal_result_for_30b(
        {
            "history": [{"step": 1, "decision": {"tool": "repo_read"}, "tool_result": {"tool": "repo_read", "ok": True}}],
            "controller_memory_write": {
                "ok": True,
                "tool": "runtime_sqlite_memory_write",
                "record_id": 4,
                "target_key": "repo",
                "db_path": "memory.sqlite",
            },
            "validation": {"evidence_contract": {"raw": True}, "ok": False},
            "planner_decision": {"raw_text": "hidden", "action": "final"},
        },
        repo_read_item_full_content=_repo_read_full_content,
    )

    assert result["history_schema"] == "agentic_terminal_public_history_ledger.v1"
    assert result["raw_history_not_inlined"] is True
    assert result["history_count"] == 1
    assert result["controller_memory_write"] == {
        "ok": True,
        "tool": "runtime_sqlite_memory_write",
        "record_id": 4,
        "target_key": "repo",
    }
    assert result["validation"] == {"ok": False}
    assert result["planner_decision"] == {"action": "final"}
