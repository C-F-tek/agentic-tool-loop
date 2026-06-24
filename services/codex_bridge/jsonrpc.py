"""JSON-RPC compatibility exports for the Codex MCP bridge.

Re-exports from repo_mcp_common.py (single source of truth).
Falls back to codex_bridge.mcp_server for raw stdio helpers only.
"""

from repo_mcp_common import handle_request as _handle_rpc
from repo_mcp_common import read_message as _read_message
from repo_mcp_common import write_message as _write_message

__all__ = ["_handle_rpc", "_read_message", "_write_message"]

