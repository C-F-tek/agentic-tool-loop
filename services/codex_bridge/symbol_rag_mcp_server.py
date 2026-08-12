"""
AICarmine Symbol RAG MCP Server

Provides MCP tools for symbol-based RAG operations.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os

SERVER_NAME = "aicarmine-symbol-rag-mcp"
SERVER_VERSION = "1.0.0"

TOOL_SCHEMAS = [
    {
        "name": "aicarmine_symbol_rag_health",
        "description": "Check symbol RAG health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "aicarmine_symbol_rag_build",
        "description": "Build symbol RAG index",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "suffixes": {"type": "string"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "aicarmine_symbol_rag_search",
        "description": "Search symbol RAG index",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["query"],
            "additionalProperties": True
        }
    },
    {
        "name": "aicarmine_symbol_rag_status",
        "description": "Get symbol RAG status",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    }
]


def handle_aicarmine_symbol_rag_health(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "server": SERVER_NAME})}]}


def handle_aicarmine_symbol_rag_build(args):
    path = args.get("path", "")
    suffixes = args.get("suffixes", "")
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "path": path, "suffixes": suffixes})}]}


def handle_aicarmine_symbol_rag_search(args):
    query = args.get("query", "")
    limit = args.get("limit", 10)
    if not query:
        return {"content": [{"type": "text", "text": json.dumps({"error": "query is required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "query": query, "results": []})}]}


def handle_aicarmine_symbol_rag_status(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "indexed_files": 0})}]}


HANDLERS = {
    "aicarmine_symbol_rag_health": handle_aicarmine_symbol_rag_health,
    "aicarmine_symbol_rag_build": handle_aicarmine_symbol_rag_build,
    "aicarmine_symbol_rag_search": handle_aicarmine_symbol_rag_search,
    "aicarmine_symbol_rag_status": handle_aicarmine_symbol_rag_status,
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