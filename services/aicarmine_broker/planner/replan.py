"""Planner replan and repair specialists."""
from typing import Any


class ReplanSpecialist:
    """Handles replan and repair operations for invalid decisions."""

    def __init__(self, config):
        self.config = config

    def repair_invalid_decision(
        self,
        goal: str,
        step: int,
        decision: dict[str, Any],
        validation: dict[str, Any],
        history: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Ask Vulkan/GPU0 for repair.

        Delegates to application/replan/specialist.vulkan_repair_invalid_planner_decision.
        """
        from ..application.replan.specialist import (
            vulkan_repair_invalid_planner_decision as _impl,
        )
        return _impl(
            goal=goal,
            step=step,
            decision=decision,
            validation=validation,
            history=history,
            state=state,
        )

    def replan_for_validation(
        self,
        goal: str,
        decision: dict[str, Any],
        validation: dict[str, Any],
        contract: dict[str, Any],
        history: list[dict[str, Any]],
        prevalidation_feedback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call replan specialist after validation failure.

        Delegates to application/planner/turn.planner_replan_specialist_for_validation.
        """
        from ..application.planner.turn import (
            planner_replan_specialist_for_validation as _replan_impl,
        )
        return _replan_impl(
            goal=goal,
            decision=decision,
            validation=validation,
            contract=contract,
            history=history,
            prevalidation_feedback=prevalidation_feedback,
        )