"""Tool dispatcher - simplified version.

This is a simplified dispatcher that removes unnecessary complexity.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RegistryToolDispatcher:
    """Simple tool dispatcher that maps names to handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, name: str, handler: Any) -> None:
        """Register a tool handler."""
        self._tools[name.lower().strip()] = handler
        logger.info("Registered tool: %s", name)

    def dispatch(self, name: str, args: dict, **kwargs: Any) -> dict[str, Any]:
        """Dispatch a tool call by name."""
        tool_name = name.lower().strip()
        handler = self._tools.get(tool_name)

        if handler is None:
            logger.warning("Unknown tool: %s", tool_name)
            return {"ok": False, "tool": tool_name, "error": "unknown internal tool"}

        try:
            logger.info("Executing tool: %s", tool_name)
            result = handler(args, **kwargs)
            logger.info("Tool %s completed", tool_name)
            return result
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return {
                "ok": False,
                "tool": tool_name,
                "error": "tool execution failed",
                "error_type": type(exc).__name__,
            }

    def list_tools(self) -> tuple[str, ...]:
        """Return sorted list of registered tool names."""
        return tuple(sorted(self._tools))