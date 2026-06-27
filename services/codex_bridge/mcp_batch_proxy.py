#!/usr/bin/env python3
"""Centralized MCP Batch Proxy — Health checks + batch tool execution with JSON compression.

This module provides a unified entry point for:
1. Health checking all 15 MCP servers
2. Executing multiple tool calls across servers in parallel batches
3. Compressing responses using bz2 JSON compression
4. Serving as a single proxy instead of calling individual MCP servers

Usage:
    from services.codex_bridge.mcp_batch_proxy import MCPBatchProxy
    
    proxy = MCPBatchProxy()
    
    # Check health of all servers
    health = proxy.health_check_all()
    
    # Execute batch operations across multiple servers
    results = proxy.execute_batch([
        {"server": "aicarmine_repo_search_det", "tool": "repo_search_rg", "args": {"path": ".", "pattern": "def \\w+"}},
        {"server": "aicarmine_repo_symbol_index", "tool": "repo_search_ctags", "args": {"path": ".", "limit": 100}},
    ])
"""

from __future__ import annotations

import bz2
import json
import os
import sys
import time
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TimeoutErrorFuture

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICES_ROOT = Path(__file__).resolve().parent
REPO_HOME_ROOT = SERVICES_ROOT.parents[1] if SERVICES_ROOT.parents else Path.cwd()

COMPRESSION_ENABLED = os.environ.get(
    "AICARMINE_MCP_COMPRESSION",
    "0"
).strip().lower() in {"1", "true", "yes", "on"}

MAX_TEXT_CHARS = int(
    os.environ.get("AICARMINE_MCP_MAX_TEXT_CHARS", "24000")
)

COMPRESS_THRESHOLD = int(
    os.environ.get("AICARMINE_MCP_COMPRESS_THRESHOLD", "10000")
)

DEBUG_MODE = os.environ.get("AICARMINE_MCP_DEBUG", "0").strip().lower() in {
    "1", "true", "yes", "on"
}


# ---------------------------------------------------------------------------
# MCP Server Registry (all 15 servers)
# ---------------------------------------------------------------------------

SERVER_SCRIPTS: Dict[str, str] = {
    "aicarmine_rag": r"C:\Users\carmi\AI\services\codex_bridge\rag_mcp_server.py",
    "aicarmine_repo_state": r"C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py",
    "aicarmine_repo_validate": r"C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py",
    "aicarmine_repo_search_det": r"C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py",
    "aicarmine_repo_code": r"C:\Users\carmi\AI\services\codex_bridge\repo_code_mcp_server.py",
    "aicarmine_codex_ops": r"C:\Users\carmi\AI\services\codex_bridge\ops_mcp_server.py",
    "aicarmine_job_view": r"C:\Users\carmi\AI\services\codex_bridge\job_view_mcp_server.py",
    "aicarmine_job_artifact": r"C:\Users\carmi\AI\services\codex_bridge\job_artifact_mcp_server.py",
    "aicarmine_git_readonly": r"C:\Users\carmi\AI\services\codex_bridge\git_readonly_mcp_server.py",
    "aicarmine_sqlite_readonly": r"C:\Users\carmi\AI\services\codex_bridge\sqlite_readonly_mcp_server.py",
    "aicarmine_project_memory": r"C:\Users\carmi\AI\services\codex_bridge\project_memory_mcp_server.py",
    "aicarmine_code_dep_graph": r"C:\Users\carmi\AI\services\codex_bridge\code_dep_graph_mcp_server.py",
    "aicarmine_repo_symbol_index": r"C:\Users\carmi\AI\services\codex_bridge\repo_symbol_index_mcp_server.py",
    "aicarmine_test_discovery": r"C:\Users\carmi\AI\services\codex_bridge\test_discovery_mcp_server.py",
    "aicarmine_index_bridge": r"C:\Users\carmi\AI\services\codex_bridge\index_bridge_mcp_server.py",
}


# ---------------------------------------------------------------------------
# Compression helpers (reuse from mcp_response_compression.py pattern)
# ---------------------------------------------------------------------------

def json_compress(value: Any) -> str:
    """Compress JSON payload using bz2. Returns hex-encoded compressed data."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    compressed = bz2.compress(raw.encode("utf-8"))
    return compressed.hex()


def json_decompress(hex_data: str) -> Any:
    """Decompress bz2-compressed JSON payload. Returns parsed JSON."""
    raw = bz2.decompress(bytes.fromhex(hex_data))
    return json.loads(raw.decode("utf-8"))


def smart_json_dumps(value: Any, *, use_compression: bool | None = None) -> str:
    """Smart JSON serialization: compresses if payload exceeds threshold."""
    if use_compression is None:
        use_compression = COMPRESSION_ENABLED
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if use_compression and len(raw) > COMPRESS_THRESHOLD:
        return f"__compressed__:{json_compress(value)}"
    return raw


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@dataclass
class ServerHealthResult:
    """Health check result for a single MCP server."""
    server_name: str
    ok: bool
    health_tool_available: bool = False
    error: str = ""
    response_time_ms: float = 0.0


def _check_server_health(server_name: str, script_path: str) -> ServerHealthResult:
    """Check health of a single MCP server by calling its health tool."""
    start_time = time.time()
    
    try:
        if not os.path.exists(script_path):
            return ServerHealthResult(
                server_name=server_name,
                ok=False,
                error=f"Script not found: {script_path}",
            )
        
        # Build all JSON-RPC messages with proper MCP handshake
        initialize_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aicarmine-mcp-batch-proxy", "version": "0.1.0-incubator"},
            }
        }
        
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        
        health_call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": f"{server_name}_health",
                "arguments": {},
            }
        }
        
        # Build frames for all three messages
        def _make_frame(msg: dict) -> bytes:
            raw = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
            header = f"Content-Length: {len(raw.encode('utf-8'))}\r\n\r\n"
            return header.encode("utf-8") + raw.encode("utf-8")
        
        frame1 = _make_frame(initialize_req)
        frame2 = _make_frame(initialized_notification)
        frame3 = _make_frame(health_call_req)
        
        # Combine all frames into a single write (same pattern as working list_servers handler)
        combined_frames = frame1 + frame2 + frame3
        
        process = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        import time as _time
        
        process.stdin.write(combined_frames)
        process.stdin.flush()
        process.stdin.close()
        
        # Read with timeout - MCP servers write and close stdout after processing
        try:
            response = process.stdout.read()
            if not response:
                raise RuntimeError(f"MCP server returned empty response")
        except Exception:
            response = b""
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        if response:
            from ops_mcp_server import _parse_mcp_messages
            messages = _parse_mcp_messages(response, "content-length")
            
            # Find the health response (id == 2)
            result_data = {}
            for msg in messages:
                if isinstance(msg, dict) and msg.get("id") == 2:
                    result_data = msg.get("result", {})
                    break
            
            return ServerHealthResult(
                server_name=server_name,
                ok=True,
                health_tool_available=True,
                response_time_ms=round(elapsed_ms, 2),
            )
        else:
            stderr_output = process.stderr.read()
            return ServerHealthResult(
                server_name=server_name,
                ok=False,
                error=f"Empty response. stderr: {stderr_output[:200]}",
                response_time_ms=round(elapsed_ms, 2),
            )
            
    except FileNotFoundError:
        return ServerHealthResult(
            server_name=server_name,
            ok=False,
            error=f"MCP server script not found: {script_path}",
        )
    except subprocess.TimeoutExpired:
        return ServerHealthResult(
            server_name=server_name,
            ok=False,
            error="Health check timed out",
        )
    except Exception as exc:
        elapsed_ms = (time.time() - start_time) * 1000
        return ServerHealthResult(
            server_name=server_name,
            ok=False,
            error=str(exc),
            response_time_ms=round(elapsed_ms, 2),
        )


# ---------------------------------------------------------------------------
# MCP Batch Proxy
# ---------------------------------------------------------------------------

class MCPBatchProxy:
    """Centralized proxy for all MCP servers with health checks and batch execution.
    
    This proxy acts as a single entry point for:
    - Health checking all 15 MCP servers
    - Executing multiple tool calls across servers in parallel batches
    - Compressing responses using bz2 JSON compression
    
    Example usage:
        proxy = MCPBatchProxy()
        
        # Check health of all servers
        health_results = proxy.health_check_all()
        
        # Execute batch operations
        results = proxy.execute_batch([
            {"server": "aicarmine_repo_search_det", "tool": "repo_search_rg", "args": {"path": ".", "pattern": "def \\w+"}},
            {"server": "aicarmine_repo_symbol_index", "tool": "repo_search_ctags", "args": {"path": ".", "limit": 100}},
        ])
    """
    
    def __init__(self, max_concurrent: int = 4, timeout_seconds: float = 60.0):
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, Any] = {}
        self._cache_stats = {"hits": 0, "misses": 0}
    
    def health_check_all(self) -> List[ServerHealthResult]:
        """Check health of all 15 MCP servers in parallel.
        
        Returns:
            List of ServerHealthResult for each server.
        """
        from concurrent.futures import ThreadPoolExecutor
        
        results = []
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {
                executor.submit(_check_server_health, server_name, script_path): server_name
                for server_name, script_path in SERVER_SCRIPTS.items()
            }
            
            for future in futures:
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    results.append(result)
                except Exception as exc:
                    results.append(ServerHealthResult(
                        server_name=futures[future],
                        ok=False,
                        error=str(exc),
                    ))
        
        return results
    
    def execute_batch(
        self,
        operations: List[Dict[str, Any]],
        use_compression: bool | None = None,
    ) -> Dict[str, Any]:
        """Execute multiple MCP tool calls across servers in parallel.
        
        Args:
            operations: List of dicts with keys 'server', 'tool', 'args'
            use_compression: Force compression (None = auto-detect)
            
        Returns:
            Dict with 'results', 'errors', 'metadata' keys.
        """
        if use_compression is None:
            use_compression = COMPRESSION_ENABLED
        
        start_time = time.time()
        results = []
        errors = []
        
        from concurrent.futures import ThreadPoolExecutor
        
        # Execute operations with concurrency limiting
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_to_op = {}
            for op in operations:
                future = executor.submit(
                    self._execute_single_tool,
                    op.get("server", ""),
                    op.get("tool", ""),
                    op.get("args", {}),
                )
                future_to_op[future] = op
            
            for future in future_to_op:
                op = future_to_op[future]
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    results.append(result)
                except TimeoutErrorFuture:
                    errors.append({
                        "server": op.get("server"),
                        "tool": op.get("tool"),
                        "error": f"Timeout after {self.timeout_seconds}s",
                    })
                except Exception as exc:
                    errors.append({
                        "server": op.get("server"),
                        "tool": op.get("tool"),
                        "error": str(exc),
                    })
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Build compressed response
        response_data = {
            "results": results,
            "errors": errors,
            "metadata": {
                "total_operations": len(operations),
                "successful": len(results),
                "failed": len(errors),
                "elapsed_ms": round(elapsed_ms, 2),
                "cache_hits": self._cache_stats["hits"],
                "compressed": use_compression,
            }
        }
        
        if use_compression:
            return {
                "ok": True,
                "data": smart_json_dumps(response_data, use_compression=use_compression),
                "metadata": response_data["metadata"],
            }
        
        return {
            "ok": True,
            "data": response_data,
            "metadata": response_data["metadata"],
        }
    
    def _execute_single_tool(
        self,
        server: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single MCP tool call via subprocess/stdio."""
        key = f"{server}:{tool_name}:{json.dumps(args, default=str)}"
        
        # Check cache
        if key in self._cache:
            self._cache_stats["hits"] += 1
            return {"server": server, "tool": tool_name, "result": self._cache[key], "cache_hit": True}
        self._cache_stats["misses"] += 1
        
        script_path = SERVER_SCRIPTS.get(server)
        if not script_path:
            raise ValueError(f"MCP server '{server}' is not configured.")
        
        start_time = time.time()
        
        try:
            # Build all JSON-RPC messages with proper MCP handshake
            initialize_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "aicarmine-mcp-batch-proxy", "version": "0.1.0-incubator"},
                }
            }
            
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            
            tools_call_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": args,
                }
            }
            
            # Build frames for all three messages
            def _make_frame(msg: dict) -> bytes:
                raw = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
                header = f"Content-Length: {len(raw.encode('utf-8'))}\r\n\r\n"
                return header.encode("utf-8") + raw.encode("utf-8")
            
            frame1 = _make_frame(initialize_req)
            frame2 = _make_frame(initialized_notification)
            frame3 = _make_frame(tools_call_req)
            
            # Combine all frames into a single write (same pattern as working list_servers handler)
            combined_frames = frame1 + frame2 + frame3
            
            process = subprocess.Popen(
                [sys.executable, "-u", script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            process.stdin.write(combined_frames)
            process.stdin.flush()
            process.stdin.close()
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            try:
                response = process.stdout.read()
                if not response:
                    raise RuntimeError(f"MCP server returned empty response")
            except Exception:
                response = b""
            
            if response:
                # Parse JSON-RPC messages from the response
                from ops_mcp_server import _parse_mcp_messages
                messages = _parse_mcp_messages(response, "content-length")
                
                # Find the tools/call response (id == 2)
                result_data = {}
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("id") == 2:
                        result_data = msg.get("result", {})
                        break
                
                self._cache[key] = result_data
                return {
                    "server": server,
                    "tool": tool_name,
                    "result": result_data,
                    "cache_hit": False,
                    "duration_ms": round(elapsed_ms, 2),
                }
            else:
                stderr_output = process.stderr.read()
                raise RuntimeError(f"MCP server returned empty response. stderr: {stderr_output[:500]}")
                
        except FileNotFoundError:
            raise RuntimeError(f"MCP server script not found: {script_path}")
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            raise RuntimeError(f"MCP tool call timed out: {server}:{tool_name}")
        except json.JSONDecodeError as exc:
            stderr_output = process.stderr.read() if process and process.stderr else ""
            raise RuntimeError(
                f"Invalid JSON response from MCP server. stderr: {stderr_output[:500]}"
            ) from exc


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for batch proxy."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Batch Proxy")
    parser.add_argument(
        "--command",
        choices=["health", "batch"],
        default="health",
        help="Command to execute",
    )
    parser.add_argument(
        "--operations",
        type=str,
        default=None,
        help="JSON array of operations (for batch command)",
    )
    args = parser.parse_args()
    
    proxy = MCPBatchProxy()
    
    if args.command == "health":
        print("Checking health of all MCP servers...")
        results = proxy.health_check_all()
        
        for result in results:
            status = "OK" if result.ok else f"FAIL: {result.error}"
            print(f"  {result.server_name}: {status} ({result.response_time_ms:.0f}ms)")
    
    elif args.command == "batch":
        if not args.operations:
            print("Usage: --operations '[{\"server\": \"...\", \"tool\": \"...\", \"args\": {...}}]'")
            return
        
        operations = json.loads(args.operations)
        print(f"Executing batch with {len(operations)} operations...")
        results = proxy.execute_batch(operations)
        
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()