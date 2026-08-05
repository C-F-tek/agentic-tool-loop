"""Planner package - coordinates planner components."""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Import classes from submodules
from .config import PlannerConfig, get_planner_config
from .prompt_builder import PromptBuilder
from .validator import PlannerValidator
from .replan import ReplanSpecialist
from .finalizer import Finalizer
from .loop import PlannerLoop

# Re-export public API functions from the coordinator file (planner.py)
# These are needed for backward compatibility when importing from aicarmine_broker.planner
def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    """Run the full agentic planner loop."""
    from ..planner import run_agentic_planner_job as _inner
    return _inner(job_id)


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a single planner decision turn."""
    from ..planner import planner_decision as _inner
    return _inner(job_id, state, step, history)


def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Finalize an agentic job."""
    from ..planner import finalize_agentic_job as _inner
    return _inner(job_id, state, status, final_summary, result)

__all__ = [
    "PlannerConfig",
    "get_planner_config",
    "PromptBuilder",
    "PlannerValidator",
    "ReplanSpecialist",
    "Finalizer",
    "PlannerLoop",
    "run_agentic_planner_job",
    "planner_decision",
    "finalize_agentic_job",
]
