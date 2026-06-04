"""Planner prompt budget/headroom calculations."""
from __future__ import annotations

from ..config import (
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
)


def prompt_compaction_threshold() -> int:
    if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET <= 0:
        return 0
    ratio = float(AGENTIC_PLANNER_PROMPT_COMPACT_RATIO or 0.5)
    ratio = max(0.1, min(ratio, 0.95))
    return max(1000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET * ratio))


def planner_token_generation_reserve(num_ctx: int | None = None) -> int:
    try:
        ctx = int(num_ctx if num_ctx is not None else AGENTIC_PLANNER_NUM_CTX)
    except Exception:
        ctx = 0
    if ctx <= 0:
        return 0
    return max(512, min(2048, ctx // 16))


def prompt_generation_headroom_char_budget() -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if budget <= 0:
        return 0
    generation_reserve = max(12000, min(18000, budget // 4))
    char_budget_limit = budget - generation_reserve
    token_budget_limit = int(max(1, AGENTIC_PLANNER_NUM_CTX - planner_token_generation_reserve()) * 2.65)
    return max(1000, min(char_budget_limit, token_budget_limit))


def prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    if compact_mode:
        sequence = (4000, 3000, 2500, 1800, 1200, 900, 700, 500)
        return sequence[min(max(0, attempt), len(sequence) - 1)]
    return max(1000, min(6000, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET // 5))
