from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.shared.clean_values import drop_empty_dict_values  # noqa: E402
from aicarmine_broker.application.shared.history_ledger import (  # noqa: E402
    history_item_ollama_turn,
    planner_history_ledger,
    planner_ollama_turn_from_decision,
)


def test_drop_empty_dict_values_removes_empty_values() -> None:
    assert drop_empty_dict_values({"a": 1, "b": "", "c": [], "d": False}) == {"a": 1, "d": False}


def test_planner_ollama_turn_from_decision_extracts_stream_meta() -> None:
    turn = planner_ollama_turn_from_decision(
        {
            "planner_stream_meta": {
                "ollama_done_seen": True,
                "ollama_done_reason": "stop",
                "ollama_eval_count": 12,
                "ollama_prompt_eval_count": 34,
            }
        },
        step=7,
    )

    assert turn == {
        "step": 7,
        "done_seen": True,
        "done_reason": "stop",
        "eval_count": 12,
        "prompt_eval_count": 34,
    }


def test_history_item_ollama_turn_reads_rejected_decision_meta() -> None:
    item = {
        "step": 4,
        "tool_result": {
            "rejected_decision": {
                "planner_stream_meta": {
                    "ollama_done_reason": "stop",
                    "ollama_prompt_eval_count": 100,
                }
            }
        },
    }

    assert history_item_ollama_turn(item) == {
        "step": 4,
        "done_reason": "stop",
        "prompt_eval_count": 100,
    }


def test_planner_history_ledger_preserves_code_product_payload() -> None:
    history = [{
        "step": 1,
        "decision": {"action": "tool", "tool": "repo_propose_code_edit", "reason": "produce diff"},
        "tool_result": {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "target_file": "a.py",
            "edit_kind": "unified_diff",
            "unified_diff": "--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n",
            "manual_review_required": True,
        },
    }]

    row = planner_history_ledger(history)[0]

    assert row["tool"] == "repo_propose_code_edit"
    assert row["target_file"] == "a.py"
    assert row["unified_diff"].startswith("---")
    assert row["manual_review_required"] is True


def test_planner_history_ledger_preserves_prompt_context_window_metadata() -> None:
    history = [{
        "step": 2,
        "decision": {"action": "tool", "tool": "planner_scratchpad_read"},
        "tool_result": {
            "tool": "planner_scratchpad_read",
            "ok": True,
            "mode": "prompt_context_window",
            "items": [{
                "document_id": "doc",
                "section": "evidence",
                "window_start": 0,
                "window_end": 20,
                "full_chars": 40,
                "window_chars": 20,
                "complete": False,
                "has_more_before": False,
                "has_more_after": True,
                "sha256": "full",
                "text": "real window",
            }],
        },
    }]

    row = planner_history_ledger(history)[0]

    assert row["mode"] == "prompt_context_window"
    assert row["items"][0]["document_id"] == "doc"
    assert row["items"][0]["window_end"] == 20
    assert row["items"][0]["text"] == "real window"
    assert row["items"][0]["window_sha256"]
