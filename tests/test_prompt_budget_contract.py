from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


import aicarmine_broker.application.prompt_budget as budget  # noqa: E402


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
