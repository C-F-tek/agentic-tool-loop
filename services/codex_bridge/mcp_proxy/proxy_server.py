"""
AICarmine MCP Proxy Server - Versione Semplificata (senza FastMCP)

Implements MCP stdio JSON-RPC transport so the proxy can be used as
a direct MCP server in Cline's cline_mcp_servers.json.

Usage:
    python services/codex_bridge/mcp_proxy/proxy_server.py

The proxy reads JSON-RPC requests from stdin and writes responses to stdout,
one JSON object per line (newline-delimited).
"""

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Support both direct execution and module invocation
try:
    from .config_minimal import ROUTE_MAP, DEFAULT_SERVER, ACTIVE_SERVERS, SERVER_SCRIPTS
    from .server_manager import ServerManager
    from .router import Router
    from .hooks import MCPHooks, HookContext
except ImportError:
    _script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(_script_dir))
    from config_minimal import ROUTE_MAP, DEFAULT_SERVER, ACTIVE_SERVERS, SERVER_SCRIPTS
    from server_manager import ServerManager
    from router import Router
    from hooks import MCPHooks, HookContext

logger = logging.getLogger(__name__)


class MCPProxyServer:
    """MCP proxy that manages subprocess connections to target MCP servers."""

    def __init__(self):
        # ServerManager.__init__() takes no args; it reads SERVER_SCRIPTS from config
        self.server_manager = ServerManager()
        # Router takes route_map as first arg; DEFAULT_SERVER is used internally via ROUTE_MAP.get("default")
        self.router = Router(ROUTE_MAP)
        self.hooks = MCPHooks()
        self._initialized = False
        self._server_info: Dict[str, Any] = {
            "protocolVersion": "2024-11-05",
            "serverName": "aicarmine-proxy",
            "serverVersion": "1.0.0",
        }

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the proxy - lightweight startup without spawning all subprocesses immediately.
        
        Deferred initialization: only start servers when first tool call is made.
        This prevents Cline connection timeout from excessive subprocess startup time.
        """
        # Don't spawn all 24 subprocess servers at init time
        # Instead, defer to first tools/list or tools/call request
        self._initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "serverCapabilities": {
                "tools": {"listChanged": False},
            },
            "serverName": "aicarmine-proxy",
            "serverVersion": "1.0.0",
        }

    async def _ensure_servers_started(self):
        """Deferred initialization - start subprocess servers on first tool call."""
        if not self._initialized or not self.server_manager._servers:
            logger.info("Starting deferred subprocess MCP servers...")
            await self.server_manager.initialize()
            self._initialized = True

    async def list_tools(self) -> List[Dict]:
        """Lista tutti i tool disponibili dai server attivi."""
        # Ensure subprocess servers are started before listing tools
        await self._ensure_servers_started()
        
        all_tools = []
        # Get active servers from ServerManager
        try:
            active = await self.server_manager.get_active_servers()
        except Exception:
            # Fallback: list all managed servers
            active = list(self.server_manager._servers.keys()) if hasattr(self.server_manager, '_servers') else []
        for server_name in active:
            try:
                tools = await self.server_manager.list_tools(server_name)
                for tool in tools:
                    tool["name"] = f"{server_name}_{tool.get('name', 'unknown')}"
                    tool["description"] = f"[{server_name}] {tool.get('description', '')}"
                    all_tools.append(tool)
            except Exception as e:
                logger.error(f"Errore list_tools per {server_name}: {e}")
        return all_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict:
        """Esegue un tool con routing e hooks."""

        # Parse tool name
        if "_" in name:
            server_name, tool_name = name.split("_", 1)
        else:
            server_name = self.router.route(name)
            tool_name = name

        # Crea contesto per hook
        context = HookContext(
            tool_name=tool_name,
            args=arguments,
            server_name=server_name
        )

        # Before hook
        try:
            hook_result = await self.hooks.before_tool_call(context)
            if hook_result:
                return hook_result
        except Exception as e:
            return await self.hooks.on_error(context, e)

        # Esegui tool
        try:
            result = await self.server_manager.call_tool(
                server_name, tool_name, arguments
            )
        except Exception as e:
            return await self.hooks.on_error(context, e)

        # After hook
        try:
            result = await self.hooks.after_tool_call(context, result)
        except Exception as e:
            logger.error(f"After hook error: {e}")

        return result

    def get_capabilities(self) -> Dict[str, Any]:
        """Return server capabilities."""
        return {
            "protocolVersion": "2024-11-05",
            "serverCapabilities": {
                "tools": {"listChanged": False},
            },
            "serverName": "aicarmine-proxy",
            "serverVersion": "1.0.0",
        }


# =============================================================================
# JSON-RPC stdio transport
# =============================================================================

async def handle_initialize(request_id: int) -> Dict:
    """Handle initialize request."""
    proxy = MCPProxyServer()
    caps = await proxy.initialize()
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": caps,
    }


async def handle_tools_list(request_id: int, proxy: MCPProxyServer) -> Dict:
    """Handle tools/list request."""
    tools = await proxy.list_tools()
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"tools": tools},
    }


async def handle_tools_call(request_id: int, arguments: Dict, proxy: MCPProxyServer) -> Dict:
    """Handle tools/call request."""
    tool_name = arguments.get("name", "")
    tool_args = arguments.get("arguments", {})
    result = await proxy.call_tool(tool_name, tool_args)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


async def jsonrpc_loop():
    """Main JSON-RPC event loop reading from stdin."""
    logging.basicConfig(level=logging.INFO)

    proxy = MCPProxyServer()
    capabilities = proxy.get_capabilities()
    logger.info("MCP Proxy server started")

    # Send initialize notification to client
    init_response = {
        "jsonrpc": "2.0",
        "result": capabilities,
    }
    # We don't send it yet - wait for client initialize

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                logger.info("stdin closed, exiting")
                break

            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                error_resp = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                print(json.dumps(error_resp), flush=True)
                continue

            method = request.get("method", "")
            request_id = request.get("id")

            if method == "initialize":
                response = await handle_initialize(request_id)
                print(json.dumps(response), flush=True)
                # Acknowledge after initialize
                ack = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                }
                print(json.dumps(ack), flush=True)

            elif method == "tools/list":
                response = await handle_tools_list(request_id, proxy)
                print(json.dumps(response), flush=True)

            elif method == "tools/call":
                params = request.get("params", {})
                response = await handle_tools_call(request_id, params, proxy)
                print(json.dumps(response), flush=True)

            else:
                logger.warning(f"Unknown method: {method}")
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                print(json.dumps(error_resp), flush=True)

        except Exception as e:
            logger.error(f"Error in JSON-RPC loop: {e}", exc_info=True)
            if request_id is not None:
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Server error: {str(e)}"},
                }
                print(json.dumps(error_resp), flush=True)


async def main():
    """Entry point for test."""
    logging.basicConfig(level=logging.INFO)

    proxy = MCPProxyServer()

    print("🔍 Lista tools...")
    tools = await proxy.list_tools()
    print(f"✅ {len(tools)} tools disponibili")
    for t in tools[:5]:
        print(f"  - {t['name']}")

    # Test call se ci sono tools
    if tools:
        print("\n🔧 Test call tool...")
        try:
            result = await proxy.call_tool(tools[0]['name'], {})
            print(f"✅ Risultato: {str(result)[:200]}...")
        except Exception as e:
            print(f"❌ Errore: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        asyncio.run(main())
    else:
        # Run JSON-RPC loop for stdio transport
        asyncio.run(jsonrpc_loop())