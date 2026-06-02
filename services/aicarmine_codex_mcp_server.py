"""Compatibility wrapper for the AI-Carmine Codex MCP server."""

from codex_bridge import mcp_server as _impl

globals().update(
    {name: value for name, value in vars(_impl).items() if not name.startswith("__")}
)
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())
