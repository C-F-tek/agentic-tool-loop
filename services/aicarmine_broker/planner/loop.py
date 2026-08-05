"""Agentic planner loop facade."""
from typing import Any


class PlannerLoop:
    """Wraps the multi-step agentic planner loop."""

    def __init__(self, config, validator, replan, finalizer):
        self.config = config
        self.validator = validator
        self.replan = replan
        self.finalizer = finalizer

    def run(self, job_id: str) -> dict[str, Any]:
        """Run the full agentic planner loop."""
        from ..application.planner.loop import (
            run_agentic_planner_job as _impl,
        )
        return _impl(job_id=job_id)

    def decision(
        self,
        job_id: str,
        state: dict[str, Any],
        step: int,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run a single planner decision turn."""
        from ..application.planner.turn import (
            planner_decision as _decision_impl,
        )
        return _decision_impl(
            job_id=job_id,
            state=state,
            step=step,
            history=history,
        )