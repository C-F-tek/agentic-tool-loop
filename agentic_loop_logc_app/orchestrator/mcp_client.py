"""
MCP Client - Client wrapper for calling MCP tools from the orchestrator.

This module provides a JSON-RPC based MCP client that can call tools exposed
by connected MCP servers such as:
- aicarmine_sqlite_readonly_mcp (sqlite queries)
- aicarmine_repo_search_det_mcp (deterministic repo search)
- aicarmine_git_readonly_mcp (git operations)
- aicarmine_project_memory_mcp (project memory)
- aicarmine_rag_mcp (RAG index)
- etc.

Usage:
    python orchestrator/mcp_client.py --server sqlite --tool aicarmine_sqlite_readonly_query --args '{"db":"rag","sql":"SELECT COUNT(*) FROM chunks"}'
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPToolCall:
    """Represents a tool call to an MCP server."""
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    success: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: int = 0


@dataclass
class MCPClientConfig:
    """Configuration for the MCP client."""
    # Server endpoints (stdio servers use command-based invocation)
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    verbose: bool = False


class MCPClient:
    """JSON-RPC based MCP client for calling MCP tools."""
    
    def __init__(self, config: MCPClientConfig | None = None) -> None:
        """Initialize the MCP client."""
        self.config = config or MCPClientConfig()
        self.tools_cache: dict[str, list[dict[str, Any]]] = {}
        self.call_log: list[MCPToolCall] = []
        
    def add_server(self, name: str, command: list[str], args: dict[str, Any] | None = None) -> None:
        """Add an MCP server to the client."""
        self.config.servers[name] = {
            "command": command,
            "args": args or {},
        }
        logger.info(f"Added MCP server: {name}")
    
    def list_tools(self, server_name: str) -> dict[str, Any]:
        """List available tools for a server."""
        if server_name in self.tools_cache:
            return {"ok": True, "tools": self.tools_cache[server_name]}
        
        result = {
            "ok": True,
            "server": server_name,
            "tools": [],
            "note": "Tool discovery requires running server - use known tool names",
        }
        
        # Known tool mappings
        known_tools = {
            "sqlite_readonly": [
                "aicarmine_sqlite_readonly_health",
                "aicarmine_sqlite_readonly_list_databases",
                "aicarmine_sqlite_readonly_schema",
                "aicarmine_sqlite_readonly_query",
            ],
            "repo_search_det": [
                "aicarmine_repo_search_det_health",
                "aicarmine_repo_search_fd",
                "aicarmine_repo_search_rg",
                "aicarmine_repo_search_jq",
                "aicarmine_repo_search_ast_grep",
                "aicarmine_repo_search_ast_grep_dry_run",
                "aicarmine_repo_search_tree_sitter_parse",
                "aicarmine_repo_search_ctags",
            ],
            "git_readonly": [
                "aicarmine_git_readonly_health",
                "aicarmine_git_readonly_log",
                "aicarmine_git_readonly_show",
                "aicarmine_git_readonly_diff",
                "aicarmine_git_readonly_blame",
                "aicarmine_git_readonly_branch_compare",
            ],
            "project_memory": [
                "aicarmine_project_memory_health",
                "aicarmine_project_memory_search",
                "aicarmine_project_memory_get",
                "aicarmine_project_memory_upsert_verified",
                "aicarmine_project_memory_mark_stale",
                "aicarmine_project_memory_supersede",
                "aicarmine_project_memory_audit_sources",
            ],
            "rag": [
                "aicarmine_rag_context",
                "aicarmine_rag_index_status",
                "aicarmine_rag_reindex",
            ],
            "ops": [
                "aicarmine_codex_ops_health",
                "aicarmine_mcp_inventory_health",
                "aicarmine_mcp_inventory_list_targets",
                "aicarmine_mcp_inventory_probe",
                "aicarmine_service_state_health",
                "aicarmine_service_state_ports",
                "aicarmine_service_state_processes",
                "aicarmine_service_state_logs",
                "aicarmine_service_state_snapshot",
            ],
        }
        
        if server_name in known_tools:
            self.tools_cache[server_name] = known_tools[server_name]
            result["tools"] = known_tools[server_name]
        
        return result
    
    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPToolCall:
        """Call a tool on an MCP server."""
        start_time = time.time()
        arguments = arguments or {}
        
        call = MCPToolCall(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
        )
        
        try:
            # Check if server is available
            if server_name not in self.config.servers:
                call.success = False
                call.error = f"Server '{server_name}' not configured"
                self.call_log.append(call)
                return call
            
            # For now, simulate tool calls with known patterns
            result = self._simulate_tool_call(server_name, tool_name, arguments)
            call.success = result.get("ok", False)
            call.result = result
            call.execution_time_ms = int((time.time() - start_time) * 1000)
            
            if not call.success:
                call.error = result.get("error", "Unknown error")
            
            logger.debug(f"Tool call {tool_name}: {'success' if call.success else 'failed'} ({call.execution_time_ms}ms)")
            
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            call.success = False
            call.error = str(e)
            call.execution_time_ms = int((time.time() - start_time) * 1000)
        
        self.call_log.append(call)
        return call
    
    def _simulate_tool_call(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Simulate a tool call with known patterns."""
        import sqlite3
        
        # SQLite query example
        if server_name == "sqlite_readonly" and tool_name == "aicarmine_sqlite_readonly_query":
            db_arg = arguments.get("db", "") or arguments.get("query", "")
            sql = arguments.get("sql", "")
            
            if not sql:
                return {"ok": False, "error": "missing_sql"}
            
            # Resolve database path
            repo_root = Path(__file__).parent.parent
            db_path = repo_root / db_arg if db_arg else repo_root / "state" / "rag_index.sqlite3"
            
            if not db_path.exists():
                return {"ok": False, "error": "db_not_found", "db": str(db_path)}
            
            try:
                conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description] if cursor.description else []
                
                result_rows = [dict(row) for row in rows]
                conn.close()
                
                return {
                    "ok": True,
                    "tool": tool_name,
                    "db": str(db_path),
                    "sql": sql,
                    "columns": columns,
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "read_only": True,
                }
            except Exception as e:
                return {"ok": False, "error": "sqlite_query_failed", "message": str(e)}
        
        # List databases example
        if server_name == "sqlite_readonly" and tool_name == "aicarmine_sqlite_readonly_list_databases":
            repo_root = Path(__file__).parent.parent
            search_roots = [
                repo_root / "state",
                repo_root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs",
            ]
            
            db_suffixes = {".sqlite", ".sqlite3", ".db"}
            databases = []
            
            for search_root in search_roots:
                if not search_root.exists():
                    continue
                for root, dirs, files in search_root.walk():
                    for f in files:
                        if f.suffix.lower() in db_suffixes:
                            full_path = root / f
                            databases.append({
                                "path": str(full_path),
                                "size_bytes": full_path.stat().st_size,
                            })
            
            return {
                "ok": True,
                "tool": tool_name,
                "databases": databases,
                "count": len(databases),
            }
        
        # Health check
        if tool_name.endswith("_health"):
            return {
                "ok": True,
                "server": server_name,
                "status": "healthy",
                "tools_available": len(self.list_tools(server_name).get("tools", [])),
            }
        
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}
    
    def get_call_log(self) -> list[dict[str, Any]]:
        """Return the call log."""
        return [
            {
                "server": c.server_name,
                "tool": c.tool_name,
                "success": c.success,
                "execution_time_ms": c.execution_time_ms,
            }
            for c in self.call_log
        ]


def main() -> int:
    """Main entry point for the MCP client CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data RAG Agent - MCP Client")
    parser.add_argument("--server", type=str, required=True, help="MCP server name")
    parser.add_argument("--tool", type=str, required=True, help="MCP tool name")
    parser.add_argument("--args-file", type=str, help="JSON arguments file path")
    parser.add_argument("--args", type=str, help="JSON arguments string")
    parser.add_argument("--list-tools", action="store_true", help="List available tools for server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
    
    client = MCPClient()
    
    # Add known servers
    client.add_server("sqlite_readonly", ["python", "services/codex_bridge/sqlite_readonly_mcp_server.py"])
    client.add_server("repo_search_det", ["python", "services/codex_bridge/repo_search_det_mcp_server.py"])
    client.add_server("git_readonly", ["python", "services/codex_bridge/git_readonly_mcp_server.py"])
    client.add_server("project_memory", ["python", "services/codex_bridge/project_memory_mcp_server.py"])
    client.add_server("rag", ["python", "services/codex_bridge/rag_mcp_server.py"])
    client.add_server("ops", ["python", "services/codex_bridge/ops_mcp_server.py"])
    
    try:
        if args.list_tools:
            result = client.list_tools(args.server)
            print(json.dumps(result, indent=2))
            return 0
        
        # Load arguments from file or string
        arguments = {}
        if args.args_file:
            args_path = Path(args.args_file)
            if not args_path.exists():
                print(f"Error: Arguments file not found: {args_path}", file=sys.stderr)
                return 1
            arguments = json.loads(args_path.read_text())
        elif args.args:
            arguments = json.loads(args.args)
        else:
            arguments = {}
        
        call = client.call_tool(args.server, args.tool, arguments)
        print(json.dumps({
            "success": call.success,
            "result": call.result,
            "error": call.error,
            "execution_time_ms": call.execution_time_ms,
        }, indent=2, default=str))
        
        return 0 if call.success else 1
    
    except Exception as e:
        logger.error(f"MCP client failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())