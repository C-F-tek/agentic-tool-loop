"""
AICarmine MCP Proxy - Router

Maps tool names to target MCP servers using the route map from config.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional

# Support both relative and absolute imports
try:
    from .config import ROUTE_MAP
except ImportError:
    # When run directly (e.g., from test script), use absolute import
    _script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(_script_dir))
    from config import ROUTE_MAP

logger = logging.getLogger(__name__)


class Router:
    """Routes tool calls to the correct MCP server."""

    def __init__(self, route_map: Optional[Dict[str, str]] = None):
        """
        Initialize the router with a route map.

        Args:
            route_map: Dictionary mapping tool name patterns to server names.
                       If None, uses the default ROUTE_MAP from config.
        """
        self._route_map = route_map or ROUTE_MAP
        # Build index for faster lookup
        self._tool_to_server: Dict[str, str] = {}
        self._build_index()

    def _build_index(self) -> None:
        """Build a direct lookup index from tool names to servers."""
        for pattern, server in self._route_map.items():
            if pattern != "default":
                self._tool_to_server[pattern] = server

    def route(self, tool_name: str) -> str:
        """
        Route a tool call to the appropriate server.

        Args:
            tool_name: The name of the tool to route.

        Returns:
            The server name that should handle this tool.

        Raises:
            KeyError: If no route is found for the tool name.
        """
        # Direct match
        if tool_name in self._tool_to_server:
            server = self._tool_to_server[tool_name]
            logger.debug(f"Tool '{tool_name}' -> Server '{server}'")
            return server

        # Partial match (check if any route pattern is contained in the tool name)
        for pattern, server in self._tool_to_server.items():
            if pattern in tool_name or tool_name.startswith(pattern):
                logger.debug(f"Tool '{tool_name}' -> Server '{server}' (partial match)")
                return server

        # Default fallback
        default_server = self._route_map.get("default", "aicarmine-codex-app")
        logger.warning(f"No route for tool '{tool_name}', using default server '{default_server}'")
        return default_server

    def get_all_servers(self) -> list:
        """Return all unique servers referenced in the route map."""
        return list(set(self._tool_to_server.values()))

    def add_route(self, tool_name: str, server_name: str) -> None:
        """Add a new route mapping."""
        self._tool_to_server[tool_name] = server_name
        self._route_map[tool_name] = server_name
        logger.info(f"Added route: '{tool_name}' -> '{server_name}'")

    def remove_route(self, tool_name: str) -> bool:
        """Remove a route mapping. Returns True if removed, False if not found."""
        if tool_name in self._tool_to_server:
            del self._tool_to_server[tool_name]
            # Also remove from route_map if present
            if tool_name in self._route_map:
                del self._route_map[tool_name]
            logger.info(f"Removed route: '{tool_name}'")
            return True
        return False

    def list_routes(self) -> Dict[str, str]:
        """Return a copy of all route mappings."""
        return dict(self._tool_to_server)