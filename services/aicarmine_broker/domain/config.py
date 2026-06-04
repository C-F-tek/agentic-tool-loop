from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    """Measured planner runtime settings for one process/turn."""

    planner_url: str
    planner_model: str
    task_url: str
    task_model: str
    num_ctx_requested: int
    num_ctx_cap: int
    num_ctx_effective: int
    prompt_char_budget: int
    prompt_compact_threshold_chars: int
    generation_headroom_reserve_chars: int
