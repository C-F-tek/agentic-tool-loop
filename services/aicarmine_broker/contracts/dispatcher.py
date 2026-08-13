from __future__ import annotations

from typing import Protocol

from ..domain import ToolDecision, ToolResult


class ToolDispatcher(Protocol):
    """Execution port for validated internal 3572 tool calls."""

    def dispatch(self, decision: ToolDecision) -> ToolResult:
        """Execute the validated tool decision and return a real payload."""
