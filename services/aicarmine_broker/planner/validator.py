"""Planner decision validator."""
from typing import Any


class PlannerValidator:
    """Validates planner decisions against evidence."""

    def __init__(self, config):
        self.config = config

    def validate(
        self,
        goal: str,
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        require_native_tool_call: bool = False,
    ) -> dict[str, Any]:
        """Validate planner decision against evidence.

        Delegates to application/planner/validator.validate_planner_decision_against_evidence.
        """
        from ..application.planner.validator import (
            validate_planner_decision_against_evidence as _impl,
        )
        return _impl(
            goal=goal,
            decision=decision,
            history=history,
            require_native_tool_call=require_native_tool_call,
        )

    def controller_guard_result(
        self,
        validation: dict[str, Any],
        decision: dict[str, Any],
        job_id: str = "",
        step: int = 0,
        goal: str = "",
    ) -> dict[str, Any]:
        """Build controller guard result."""
        from ..application.planner.validator import (
            controller_guard_result_for_validation as _guard_impl,
        )
        return _guard_impl(
            validation=validation,
            decision=decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )