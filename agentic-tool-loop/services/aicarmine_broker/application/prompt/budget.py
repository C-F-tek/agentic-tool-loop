"""Planner prompt budget/headroom calculations."""
from __future__ import annotations

import json
from typing import Any

from ...config import (
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
)

PROMPT_CHARS_PER_TOKEN = 2.65


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
    return max(512, min(32768, ctx // 16))


def prompt_generation_headroom_char_budget() -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if budget <= 0:
        return 0
    generation_reserve = int(planner_token_generation_reserve() * PROMPT_CHARS_PER_TOKEN)
    generation_reserve = max(12000, min(max(12000, budget // 3), generation_reserve))
    char_budget_limit = budget - generation_reserve
    token_budget_limit = int(max(1, AGENTIC_PLANNER_NUM_CTX - planner_token_generation_reserve()) * PROMPT_CHARS_PER_TOKEN)
    return max(1000, min(char_budget_limit, token_budget_limit))


def prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if compact_mode:
        base = max(4000, min(64000, budget // 16 if budget > 0 else 4000))
        sequence = (
            base,
            int(base * 0.75),
            int(base * 0.60),
            int(base * 0.45),
            int(base * 0.30),
            int(base * 0.20),
            int(base * 0.15),
            int(base * 0.10),
        )
        return sequence[min(max(0, attempt), len(sequence) - 1)]
    return max(1000, min(96000, budget // 8 if budget > 0 else 6000))


def _json_char_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def prompt_budget_report(
    user_payload: dict[str, Any],
    *,
    system_prompt: str = "",
    extra_prompt_sections: dict[str, int] | None = None,
) -> dict[str, Any]:
    sections = {
        key: _json_char_len(value)
        for key, value in user_payload.items()
        if key not in {"available_tools"}
    }
    sections["available_tools"] = _json_char_len(user_payload.get("available_tools"))
    extra_sections = {
        str(key): int(value)
        for key, value in (extra_prompt_sections or {}).items()
        if int(value or 0) > 0
    }
    sections.update(extra_sections)
    total_user = _json_char_len(user_payload)
    system_chars = len(str(system_prompt or ""))
    extra_chars = sum(extra_sections.values())
    total = total_user + system_chars + extra_chars
    headroom_budget = prompt_generation_headroom_char_budget()
    generation_reserve = max(0, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET - headroom_budget)
    return {
        "schema": "planner_prompt_budget.v1",
        "char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
        "generation_headroom_char_budget": headroom_budget,
        "generation_headroom_reserve_chars": generation_reserve,
        "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
        "generation_token_reserve": planner_token_generation_reserve(),
        "system_prompt_chars": system_chars,
        "total_user_payload_chars": total_user,
        "extra_prompt_chars": extra_chars,
        "total_prompt_chars": total,
        "over_budget": bool(
            AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
            and total > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        ),
        "over_generation_headroom_budget": bool(headroom_budget > 0 and total > headroom_budget),
        "sections": sections,
    }


def report_exceeds_generation_headroom(report: dict[str, Any], headroom_char_budget: int) -> bool:
    if int(headroom_char_budget or 0) <= 0:
        return False
    total = int((report or {}).get("total_prompt_chars") or 0)
    if total <= int(headroom_char_budget):
        return False
    native_reserve = int((report or {}).get("native_history_reserve_chars") or 0)
    if native_reserve > 0 and max(0, total - native_reserve) <= int(headroom_char_budget):
        return False
    return True
