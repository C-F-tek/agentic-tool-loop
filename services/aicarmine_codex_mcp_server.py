"""Compatibility wrapper for the AI-Carmine Codex MCP server."""

from codex_bridge.mcp_server import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
