from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from ..domain import ToolResult


@runtime_checkable
class AgenticTool(Protocol):
    """Callable internal tool boundary."""

    name: str

    def schema(self) -> Mapping[str, Any]:
        """Return the planner-visible JSON schema for this tool."""

    def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        """Execute and return the complete internal tool payload."""
