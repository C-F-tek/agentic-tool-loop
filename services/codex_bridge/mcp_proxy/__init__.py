"""
AICarmine MCP Proxy Server

Aggregates multiple MCP servers behind a single stdio endpoint.
Provides routing, hooks, logging, and rate limiting.
"""

from .config import TARGET_SERVERS, SERVER_SCRIPTS, ROUTE_MAP
from .router import Router
from .hooks import HookContext, MCPHooks
from .server_manager import ServerManager
from .proxy_server import MCPProxyServer

__all__ = [
    "TARGET_SERVERS",
    "SERVER_SCRIPTS",
    "ROUTE_MAP",
    "Router",
    "HookContext",
    "MCPHooks",
    "ServerManager",
    "MCPProxyServer",
]