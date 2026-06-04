from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.planner_status import (  # noqa: E402
    planner_done_token,
    summarize_history_artifacts,
)


def test_planner_done_token_accepts_existing_completion_tokens() -> None:
    assert planner_done_token(" `DONE.` ")
    assert planner_done_token("completato")
    assert planner_done_token("выполнено")


def test_planner_done_token_rejects_non_terminal_text() -> None:
    assert not planner_done_token("done after I read another file")
    assert not planner_done_token('{"action":"final","final_answer":"done"}')


def test_summarize_history_artifacts_keeps_last_ten_rows_and_shape() -> None:
    history = [
        {
            "step": step,
            "tool_result": {
                "tool": "repo_read",
                "ok": True,
                "artifact": f"reads/{step}.json",
                "path": f"pkg/{step}.py",
                "ignored": "not public status",
            },
        }
        for step in range(12)
    ]

    summary = summarize_history_artifacts(history)

    assert len(summary) == 10
    assert summary[0]["step"] == 2
    assert summary[-1] == {
        "step": 11,
        "tool": "repo_read",
        "ok": True,
        "artifact": "reads/11.json",
        "path": "pkg/11.py",
    }


def test_summarize_history_artifacts_ignores_non_tool_rows() -> None:
    assert summarize_history_artifacts([
        {"step": 1},
        {"step": 2, "tool_result": {"ok": True}},
        {"step": 3, "tool_result": "not-a-dict"},
    ]) == []
