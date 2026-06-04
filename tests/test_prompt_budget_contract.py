from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


import aicarmine_broker.application.prompt.budget as budget  # noqa: E402


def test_planner_token_generation_reserve_clamps() -> None:
    assert budget.planner_token_generation_reserve(0) == 0
    assert budget.planner_token_generation_reserve(1024) == 512
    assert budget.planner_token_generation_reserve(65536) == 2048


def test_prompt_compaction_threshold_uses_clamped_ratio(monkeypatch) -> None:
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET", 10000)
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO", 2.0)

    assert budget.prompt_compaction_threshold() == 9500


def test_prompt_generation_headroom_keeps_generation_reserve(monkeypatch) -> None:
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET", 48000)
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_NUM_CTX", 12288)

    assert budget.prompt_generation_headroom_char_budget() == 30528


def test_prompt_window_chars_sequence() -> None:
    assert budget.prompt_window_chars(True, 0) == 4000
    assert budget.prompt_window_chars(True, 100) == 500
    assert budget.prompt_window_chars(False) >= 1000


def test_prompt_budget_report_counts_sections_and_headroom(monkeypatch) -> None:
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET", 1000)
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_NUM_CTX", 1024)

    report = budget.prompt_budget_report(
        {"goal": "x", "available_tools": [{"name": "repo_read"}]},
        system_prompt="system",
        extra_prompt_sections={"native_tools_schema": 120, "empty": 0},
    )

    assert report["schema"] == "planner_prompt_budget.v1"
    assert report["char_budget"] == 1000
    assert report["num_ctx_effective"] == 1024
    assert report["generation_token_reserve"] == 512
    assert report["system_prompt_chars"] == len("system")
    assert report["extra_prompt_chars"] == 120
    assert report["sections"]["native_tools_schema"] == 120
    assert "empty" not in report["sections"]
    assert report["sections"]["available_tools"] > 0


def test_prompt_budget_report_marks_over_budget(monkeypatch) -> None:
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET", 20000)
    monkeypatch.setattr(budget, "AGENTIC_PLANNER_NUM_CTX", 1024)

    report = budget.prompt_budget_report({"goal": "x" * 22000})

    assert report["over_budget"] is True
    assert report["over_generation_headroom_budget"] is True


def test_report_exceeds_generation_headroom_accounts_for_native_history_reserve() -> None:
    assert budget.report_exceeds_generation_headroom(
        {"total_prompt_chars": 1200},
        1000,
    ) is True
    assert budget.report_exceeds_generation_headroom(
        {"total_prompt_chars": 1200, "native_history_reserve_chars": 300},
        1000,
    ) is False
    assert budget.report_exceeds_generation_headroom(
        {"total_prompt_chars": 1200},
        0,
    ) is False
