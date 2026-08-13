from __future__ import annotations

from typing import Protocol

from ..domain import ToolDecision, ToolResult


class ToolDispatcher(Protocol):
    """Execution port for validated internal 3572 tool calls.

    Defines the interface that dispatcher implementations must provide
    for executing planner decisions as internal broker tools.
    """

    def dispatch(self, decision: ToolDecision) -> ToolResult:
        """Execute the validated tool decision and return a real payload.

        Args:
            decision: The normalized planner decision containing tool name,
                arguments, and reason.
        Returns:
            A ToolResult representing the tool execution outcome.
        """
