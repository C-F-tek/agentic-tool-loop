#!/usr/bin/env python3
"""MCP Batch Proxy Server — Exposed MCP tool for parallel batch execution across all servers.

This MCP server exposes 3 tools:
1. mcp_batch_health — Health check all 15 MCP servers in one call
2. mcp_batch_list_servers — List available servers and their tools
3. mcp_batch_execute — Execute multiple tool calls across servers in parallel

Usage:
    # Via MCP (Cline use_mcp_tool):
    use_mcp_tool("aicarmine_codex_ops", "mcp_batch_execute", {
        "operations": [
            {"server": "aicarmine_repo_search_det", "tool": "repo_search_rg", "args": {"path": ".", "pattern": "def \\w+"}},
            {"server": "aicarmine_repo_symbol_index", "tool": "repo_search_ctags", "args": {"path": ".", "limit": 100}}
        ]
    })

    # Via CLI:
    python mcp_batch_proxy_server.py --self-test
"""

from __future__ import annotations

import bz2
import json
import os
import sys
import time
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TimeoutErrorFuture
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import shared utilities
from repo_mcp_common import (
    ToolSpec,
    boolean_prop,
    health_payload,
    integer_prop,
    object_schema,
    serve,
    string_array_prop,
)

# Import batch proxy logic
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_batch_proxy import (
    SERVER_SCRIPTS,
    COMPRESSION_ENABLED,
    COMPRESS_THRESHOLD,
    MAX_TEXT_CHARS,
    json_compress,
    json_decompress,
    smart_json_dumps,
    _check_server_health,
    MCPBatchProxy,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_NAME = "aicarmine-mcp-batch-proxy"
SERVER_VERSION = "0.1.0-incubator"


# ---------------------------------------------------------------------------
# Batch Execute Handler
# ---------------------------------------------------------------------------

def _mcp_batch_execute_handler(args: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Execute multiple MCP tool calls across servers in parallel."""
    proxy = MCPBatchProxy(max_concurrent=4, timeout_seconds=60.0)
    
    operations = args.get("operations", [])
    if not isinstance(operations, list):
        return {
            "ok": False,
            "error": "operations must be a list",
            "tool": "mcp_batch_execute",
        }
    
    # Validate and sanitize operations
    validated_ops = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        server = str(op.get("server", "")).strip()
        tool = str(op.get("tool", "")).strip()
        op_args = op.get("args", {})
        if not isinstance(op_args, dict):
            op_args = {}
        
        # Check server is allowed
        if server not in SERVER_SCRIPTS:
            continue
        
        validated_ops.append({
            "server": server,
            "tool": tool,
            "args": op_args,
        })
    
    use_compression = args.get("compress", False) or COMPRESSION_ENABLED
    
    start_time = time.time()
    results = []
    errors = []
    
    with ThreadPoolExecutor(max_workers=min(4, len(validated_ops))) as executor:
        future_to_op = {}
        for op in validated_ops:
            future = executor.submit(
                proxy._execute_single_tool,
                op["server"],
                op["tool"],
                op["args"],
            )
            future_to_op[future] = op
        
        for future in future_to_op:
            op = future_to_op[future]
            try:
                result = future.result(timeout=60.0)
                results.append(result)
            except TimeoutErrorFuture:
                errors.append({
                    "server": op["server"],
                    "tool": op["tool"],
                    "error": "timeout",
                })
            except Exception as exc:
                errors.append({
                    "server": op["server"],
                    "tool": op["tool"],
                    "error": str(exc),
                })
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    response_data = {
        "results": results,
        "errors": errors,
        "metadata": {
            "total_operations": len(validated_ops),
            "successful": len(results),
            "failed": len(errors),
            "elapsed_ms": round(elapsed_ms, 2),
            "cache_hits": proxy._cache_stats["hits"],
            "compressed": use_compression,
        }
    }
    
    if use_compression:
        compressed = smart_json_dumps(response_data, use_compression=True)
        return {
            "ok": True,
            "tool": "mcp_batch_execute",
            "data": compressed,
            "metadata": response_data["metadata"],
        }
    
    return {
        "ok": True,
        "tool": "mcp_batch_execute",
        "results": results,
        "errors": errors,
        "metadata": response_data["metadata"],
    }


def _mcp_batch_health_handler(args: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Health check all 15 MCP servers in parallel."""
    proxy = MCPBatchProxy(max_concurrent=4, timeout_seconds=30.0)
    
    servers = args.get("servers")
    if isinstance(servers, list) and servers:
        # Filter to only valid servers
        servers = [s for s in servers if s in SERVER_SCRIPTS]
        if not servers:
            servers = list(SERVER_SCRIPTS.keys())
    else:
        servers = list(SERVER_SCRIPTS.keys())
    
    start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_server = {
            executor.submit(_check_server_health, server, script): server
            for server, script in SERVER_SCRIPTS.items()
            if server in servers
        }
        
        for future in future_to_server:
            try:
                result = future.result(timeout=30.0)
                results.append(result)
            except Exception:
                results.append({
                    "server_name": future_to_server[future],
                    "ok": False,
                    "error": "health_check_failed",
                })
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    healthy_count = sum(1 for r in results if r.ok)
    unhealthy_count = len(results) - healthy_count
    
    return {
        "ok": True,
        "tool": "mcp_batch_health",
        "servers": results,
        "server_count": len(results),
        "healthy": healthy_count,
        "unhealthy": unhealthy_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _mcp_batch_list_servers_handler(args: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """List available MCP servers and their tools."""
    from ops_mcp_server import _parse_mcp_messages, _frame
    
    servers_info = []
    
    for server_name, script_path in sorted(SERVER_SCRIPTS.items()):
        script = Path(script_path)
        if not script.is_file():
            servers_info.append({
                "name": server_name,
                "script": str(script),
                "available": False,
                "error": "script_not_found",
            })
            continue
        
        # Probe to get tools list
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            frames = [
                _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                        },
                    },
                    "content-length",
                ),
                _frame({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, "content-length"),
                _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, "content-length"),
            ]
            
            process.stdin.write(b"".join(frames))
            process.stdin.flush()
            
            response = process.stdout.read()
            process.stdin.close()
            
            messages = _parse_mcp_messages(response, "content-length")
            tools = []
            for msg in messages:
                if msg.get("id") == 2:
                    raw_result = msg.get("result", {})
                    raw_tools = raw_result.get("tools", [])
                    tools = [t.get("name") for t in raw_tools if isinstance(t, dict) and isinstance(t.get("name"), str)]
                    break
            
            servers_info.append({
                "name": server_name,
                "script": str(script),
                "available": True,
                "tool_count": len(tools),
                "tools": sorted(tools)[:20],  # Limit to first 20 tools
            })
        except Exception as exc:
            servers_info.append({
                "name": server_name,
                "script": str(script),
                "available": False,
                "error": str(exc),
            })
    
    return {
        "ok": True,
        "tool": "mcp_batch_list_servers",
        "servers": servers_info,
        "server_count": len(servers_info),
        "total_tools": sum(1 for s in servers_info if s.get("available")),
    }


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------

def _tools() -> Dict[str, ToolSpec]:
    tools: Dict[str, ToolSpec] = {}
    
    def health(args: Dict[str, Any], root: Path) -> Dict[str, Any]:
        payload = health_payload(SERVER_NAME, ["mcp_batch_health", "mcp_batch_list_servers", "mcp_batch_execute"])
        payload["incubation_status"] = "isolated_candidate"
        payload["tool_groups"] = ["aicarmine_mcp_batch_proxy"]
        payload["no_http_probes"] = True
        return payload
    
    tools["mcp_batch_health"] = ToolSpec(
        name="mcp_batch_health",
        description="Health check all 15 MCP servers in parallel. Returns status of each server.",
        input_schema=object_schema({
            "servers": string_array_prop(),
        }),
        handler=_mcp_batch_health_handler,
    )
    
    tools["mcp_batch_list_servers"] = ToolSpec(
        name="mcp_batch_list_servers",
        description="List available MCP servers and their tools.",
        input_schema=object_schema(),
        handler=_mcp_batch_list_servers_handler,
    )
    
    tools["mcp_batch_execute"] = ToolSpec(
        name="mcp_batch_execute",
        description="Execute multiple MCP tool calls across servers in parallel. Each operation has {server, tool, args}.",
        input_schema=object_schema({
            "operations": {
                "type": "array",
                "items": object_schema({
                    "server": {"type": "string"},
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                }),
            },
            "compress": boolean_prop(False),
        }),
        handler=_mcp_batch_execute_handler,
    )
    
    return tools


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    
    if "--self-test" in argv:
        print(json.dumps({
            "ok": True,
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "tools": sorted(tools),
            "description": "MCP Batch Proxy — Health check + batch execution across all servers",
        }, indent=2))
        return 0
    
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())