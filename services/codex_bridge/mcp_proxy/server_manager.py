"""
AICarmine MCP Proxy - Server Manager

Manages subprocess connections to target MCP servers.
Uses stdio transport via subprocess for each target server.
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Support both relative and absolute imports
try:
    from .config import SERVER_SCRIPTS, BASE_DIR
except ImportError:
    _script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(_script_dir))
    from config import SERVER_SCRIPTS, BASE_DIR

logger = logging.getLogger(__name__)


class ServerProcess:
    """Represents a single MCP server subprocess."""

    def __init__(self, server_name: str, script_path: str):
        self.server_name = server_name
        self.script_path = script_path
        self.process: Optional[subprocess.Popen] = None
        self._stdin: Optional[Any] = None
        self._stdout: Optional[Any] = None
        self._running: bool = False
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start the server subprocess."""
        try:
            # SERVER_SCRIPTS paths are relative to workspace root (parent of services/)
            _proxy_dir = Path(__file__).resolve().parent
            _workspace_root = _proxy_dir.parent.parent
            full_path = str(_workspace_root / self.script_path)
            
            cmd = [
                sys.executable or r"C:\Users\sanit\AppData\Local\Programs\Python\Python312\python.exe",
                "-u",
                full_path
            ]

            env = {
                "AICARMINE_CODEX_MCP_REPO_ROOT": ".",
                "AICARMINE_LAB_REPO": ".",
                "AICARMINE_MCP_GZIP_ENABLED": "1",
                "AICARMINE_MCP_GZIP_THRESHOLD": "8192",
                "PATH": r"C:\Users\sanit\AppData\Local\Programs\Python\Python314;C:\Users\sanit\AppData\Local\Programs\Python\Python314\Scripts;%PATH%",
            }
            env.update(dict.__getitem__.__call__(__builtins__, "get") if False else {})

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(BASE_DIR),
            )

            self.process = process
            self._stdin = process.stdin
            self._stdout = process.stdout
            self._running = True

            logger.info(f"Started server '{self.server_name}' with PID {process.pid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start server '{self.server_name}': {e}")
            self._running = False
            return False

    async def stop(self) -> bool:
        """Stop the server subprocess."""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self._running = False
                logger.info(f"Stopped server '{self.server_name}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to stop server '{self.server_name}': {e}")
            return False

    async def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send an MCP request and wait for response."""
        if not self._running or not self.process:
            raise RuntimeError(f"Server '{self.server_name}' is not running")

        json_data = json.dumps(request) + "\n"
        
        try:
            if self._stdin:
                self._stdin.write(json_data.encode())
                self._stdin.flush()

            # Read response line
            if self._stdout:
                line = self._stdout.readline()
                if not line:
                    raise RuntimeError(f"Server '{self.server_name}' closed connection")
                
                response = json.loads(line.strip())
                return response

        except Exception as e:
            self._running = False
            raise RuntimeError(f"Communication error with '{self.server_name}': {e}")

    @property
    def is_running(self) -> bool:
        """Check if the server process is still running."""
        if self.process:
            return self.process.poll() is None
        return False


class ServerManager:
    """Manages multiple MCP server subprocesses."""

    def __init__(self):
        self._servers: Dict[str, ServerProcess] = {}
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize all target servers."""
        success = True
        for server_name, script_path in SERVER_SCRIPTS.items():
            server = ServerProcess(server_name, script_path)
            self._servers[server_name] = server
            
            started = await server.start()
            if not started:
                logger.error(f"Failed to initialize server '{server_name}'")
                success = False
            else:
                logger.info(f"Server '{server_name}' initialized successfully")
        
        self._initialized = success
        return success

    async def get_server(self, server_name: str) -> Optional[ServerProcess]:
        """Get a server process by name."""
        return self._servers.get(server_name)

    async def list_servers(self) -> List[str]:
        """List all managed server names."""
        return list(self._servers.keys())

    async def get_active_servers(self) -> List[str]:
        """List all running server names."""
        return [name for name, proc in self._servers.items() if proc.is_running]

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call a tool on the specified server.
        
        Uses MCP protocol: send initialize, then callTool request.
        """
        server = self._servers.get(server_name)
        if not server:
            raise KeyError(f"Server '{server_name}' not found")
        
        if not server.is_running:
            raise RuntimeError(f"Server '{server_name}' is not running")

        # Build MCP callTool request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            }
        }

        response = await server.send_request(request)
        return response

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """List all tools available from a server."""
        server = self._servers.get(server_name)
        if not server:
            raise KeyError(f"Server '{server_name}' not found")
        
        if not server.is_running:
            raise RuntimeError(f"Server '{server_name}' is not running")

        # Build MCP tools/list request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }

        response = await server.send_request(request)
        
        # Extract tools from response
        tools = []
        if "result" in response:
            result = response["result"]
            if "tools" in result:
                tools = result["tools"]
        
        return tools

    async def stop_all(self) -> None:
        """Stop all managed servers."""
        for name, server in self._servers.items():
            await server.stop()
        self._servers.clear()
        logger.info("All servers stopped")

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all servers."""
        results = {}
        for name, server in self._servers.items():
            results[name] = server.is_running
        return results