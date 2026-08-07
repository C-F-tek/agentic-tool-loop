#!/usr/bin/env python
"""Self-test for the agentic loop client MCP server."""
import sys
sys.path.insert(0, '.')

from codex_bridge.agentic_loop_client_mcp_server import main
exit(main(['--self-test']))