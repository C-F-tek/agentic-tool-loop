from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from ..domain import ToolResult


@runtime_checkable
class AgenticTool(Protocol):
    """Callable internal tool boundary.

    Defines the interface that all internal 3572 broker tools must implement,
    providing a name, JSON schema for the planner, and an execute method
    that returns a bounded ToolResult.
    """

    name: str

    def schema(self) -> Mapping[str, Any]:
        """Return the planner-visible JSON schema for this tool.

        Returns:
            A mapping representing the tool's argument schema.
        """

    def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        """Execute and return the complete internal tool payload.

        Args:
            arguments: The tool arguments from the planner decision.
        Returns:
            A ToolResult representing the execution outcome.
        """
