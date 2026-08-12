"""
AICarmine MCP Batch Proxy Server

Provides batch execution tools for MCP tool calls.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os

SERVER_NAME = "aicarmine-batch-mcp"
SERVER_VERSION = "1.0.0"

TOOL_SCHEMAS = [
    {
        "name": "batch_execute",
        "description": "Execute a batch of MCP tool calls",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tools": {"type": "array", "items": {"type": "object"}},
                "arguments": {"type": "array", "items": {"type": "object"}}
            },
            "required": ["tools"],
            "additionalProperties": True
        }
    },
    {
        "name": "health_check",
        "description": "Check batch server health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "mcp_batch_health",
        "description": "Check MCP batch health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "mcp_batch_list_servers",
        "description": "List available MCP servers for batch",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "mcp_batch_execute",
        "description": "Execute MCP batch operation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "tool": {"type": "string"},
                "args": {"type": "object"}
            },
            "required": ["server", "tool"],
            "additionalProperties": True
        }
    }
]


def handle_batch_execute(args):
    tools = args.get("tools", [])
    arguments = args.get("arguments", [])
    if not tools:
        return {"content": [{"type": "text", "text": json.dumps({"error": "tools is required"})}], "isError": True}
    try:
        results = []
        for i, tool in enumerate(tools):
            result = {"tool": tool.get("name", ""), "status": "simulated"}
            if arguments and i < len(arguments):
                result["args"] = arguments[i]
            results.append(result)
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "results": results})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_health_check(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "server": SERVER_NAME})}]}


def handle_mcp_batch_health(args):
    return {"content": [{"type": "text", "text": json.dumps({"ok": True, "server": SERVER_NAME, "mode": "batch_proxy"})}]}


def handle_mcp_batch_list_servers(args):
    servers = [
        "aicarmine-codex-app",
        "aicarmine-repo-state",
        "aicarmine-repo-search-det",
        "aicarmine-project-memory",
        "aicarmine-sqlite-readonly",
        "aicarmine-rag",
        "aicarmine-job-artifact",
        "aicarmine-job-view",
        "aicarmine-codex-ops",
        "aicarmine-local-subagent",
        "aicarmine-agentic-loop-client",
        "aicarmine-git-readonly"
    ]
    return {"content": [{"type": "text", "text": json.dumps({"servers": servers})}]}


def handle_mcp_batch_execute(args):
    server = args.get("server", "")
    tool = args.get("tool", "")
    if not server or not tool:
        return {"content": [{"type": "text", "text": json.dumps({"error": "server and tool are required"})}], "isError": True}
    try:
        result = {
            "server": server,
            "tool": tool,
            "status": "simulated",
            "args": args.get("args", {})
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


HANDLERS = {
    "batch_execute": handle_batch_execute,
    "health_check": handle_health_check,
    "mcp_batch_health": handle_mcp_batch_health,
    "mcp_batch_list_servers": handle_mcp_batch_list_servers,
    "mcp_batch_execute": handle_mcp_batch_execute,
}


def main():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        line = stdin.readline()
        if not line:
            break
        message = json.loads(line.decode("utf-8-sig", errors="replace"))
        msg_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {}) if isinstance(message.get("params"), dict) else {}

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                        "roots": {"listChanged": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method == "tools/list":
            response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_SCHEMAS}}
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {}) if isinstance(params.get("arguments"), dict) else {}
            handler = HANDLERS.get(name)
            if handler:
                try:
                    result = handler(arguments)
                except Exception as e:
                    result = {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
                response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            else:
                response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method.startswith("notifications/"):
            continue

    return 0


if __name__ == "__main__":
    raise SystemExit(main())