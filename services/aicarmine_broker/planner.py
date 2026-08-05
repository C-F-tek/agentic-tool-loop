"""Planner facade - coordinates planner components.

This file is the single entry point for planner operations.
All implementation details are delegated to modules under planner/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .planner.config import get_planner_config
from .planner.prompt_builder import PromptBuilder
from .planner.validator import PlannerValidator
from .planner.replan import ReplanSpecialist
from .planner.finalizer import Finalizer
from .planner.loop import PlannerLoop

# ---------------------------------------------------------------------------
# Singleton component initialization
# ---------------------------------------------------------------------------

_config = get_planner_config()
_prompt_builder = PromptBuilder(_config)
_validator = PlannerValidator(_config)
_replan = ReplanSpecialist(_config)
_finalizer = Finalizer(_config)
_loop = PlannerLoop(_config, _validator, _replan, _finalizer)


def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    """Run the full agentic planner loop."""
    return _loop.run(job_id)


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a single planner decision turn."""
    return _loop.decision(job_id, state, step, history)


def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Finalize an agentic job."""
    return _finalizer.finalize(
        job_id=job_id,
        state=state,
        status=status,
        final_summary=final_summary,
        result=result,
    )


# ---------------------------------------------------------------------------
# Re-export for backward compatibility
# ---------------------------------------------------------------------------

__all__ = [
    "run_agentic_planner_job",
    "planner_decision",
    "finalize_agentic_job",
]