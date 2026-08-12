"""
AICarmine Refactor MCP Server

Provides MCP tools for code refactoring operations.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os

SERVER_NAME = "aicarmine-refactor-mcp"
SERVER_VERSION = "1.0.0"

TOOL_SCHEMAS = [
    {
        "name": "git_list_tracked_files",
        "description": "List tracked files in the repository",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "refactor_add_parameter",
        "description": "Add a parameter to a function",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "function": {"type": "string"},
                "parameter": {"type": "string"}
            },
            "required": ["file", "function", "parameter"],
            "additionalProperties": True
        }
    },
    {
        "name": "refactor_extract_function",
        "description": "Extract code into a new function",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "new_function_name": {"type": "string"}
            },
            "required": ["file", "start_line", "end_line", "new_function_name"],
            "additionalProperties": True
        }
    },
    {
        "name": "refactor_health",
        "description": "Check refactor server health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "refactor_rename_project",
        "description": "Rename project references",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_name": {"type": "string"},
                "new_name": {"type": "string"}
            },
            "required": ["old_name", "new_name"],
            "additionalProperties": True
        }
    },
    {
        "name": "refactor_rename_project_bowler",
        "description": "Rename project using bowler",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "replacement": {"type": "string"}
            },
            "required": ["pattern", "replacement"],
            "additionalProperties": True
        }
    },
    {
        "name": "refactor_rename_symbol",
        "description": "Rename a symbol in the codebase",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "old_name": {"type": "string"},
                "new_name": {"type": "string"}
            },
            "required": ["file", "old_name", "new_name"],
            "additionalProperties": True
        }
    },
    {
        "name": "refactor_rename_symbol_rope",
        "description": "Rename a symbol using rope",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "old_name": {"type": "string"},
                "new_name": {"type": "string"}
            },
            "required": ["file", "old_name", "new_name"],
            "additionalProperties": True
        }
    }
]


def handle_git_list_tracked_files(args):
    try:
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT", os.getcwd())
        )
        files = result.stdout.strip().split("\n") if result.returncode == 0 else []
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "files": files})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_refactor_add_parameter(args):
    file = args.get("file", "")
    function = args.get("function", "")
    parameter = args.get("parameter", "")
    if not file or not function or not parameter:
        return {"content": [{"type": "text", "text": json.dumps({"error": "file, function, and parameter are required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "file": file, "function": function, "parameter": parameter})}]}


def handle_refactor_extract_function(args):
    file = args.get("file", "")
    start_line = args.get("start_line", 0)
    end_line = args.get("end_line", 0)
    new_function_name = args.get("new_function_name", "")
    if not file or not start_line or not end_line or not new_function_name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "All fields required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "file": file, "extracted": new_function_name})}]}


def handle_refactor_health(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "server": SERVER_NAME})}]}


def handle_refactor_rename_project(args):
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    if not old_name or not new_name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "old_name and new_name are required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "old": old_name, "new": new_name})}]}


def handle_refactor_rename_project_bowler(args):
    pattern = args.get("pattern", "")
    replacement = args.get("replacement", "")
    if not pattern or not replacement:
        return {"content": [{"type": "text", "text": json.dumps({"error": "pattern and replacement are required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "pattern": pattern, "replacement": replacement})}]}


def handle_refactor_rename_symbol(args):
    file = args.get("file", "")
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    if not file or not old_name or not new_name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "file, old_name, and new_name are required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "file": file, "old": old_name, "new": new_name})}]}


def handle_refactor_rename_symbol_rope(args):
    file = args.get("file", "")
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    if not file or not old_name or not new_name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "file, old_name, and new_name are required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "file": file, "old": old_name, "new": new_name})}]}


HANDLERS = {
    "git_list_tracked_files": handle_git_list_tracked_files,
    "refactor_add_parameter": handle_refactor_add_parameter,
    "refactor_extract_function": handle_refactor_extract_function,
    "refactor_health": handle_refactor_health,
    "refactor_rename_project": handle_refactor_rename_project,
    "refactor_rename_project_bowler": handle_refactor_rename_project_bowler,
    "refactor_rename_symbol": handle_refactor_rename_symbol,
    "refactor_rename_symbol_rope": handle_refactor_rename_symbol_rope,
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