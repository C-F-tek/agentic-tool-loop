#!/usr/bin/env python3
"""
MCP server for Python refactoring operations.
Wraps libcst and rope refactoring tools as MCP-compatible operations.

Provides:
- tools/list → returns available refactoring tools
- tools/call → executes refactoring operations
- resources/list → returns refactoring templates
- resources/read → reads template content
"""
import json
import sys
from pathlib import Path
from typing import Any

# Import our refactor tools
sys.path.insert(0, str(Path(__file__).parent.parent))
from codex_bridge.refactor_tools import (
    HAS_BOWLER,
    HAS_LIBCST,
    HAS_ROPE,
    RefactorResult,
    git_list_tracked_files,
    refactor_add_parameter,
    refactor_extract_function,
    refactor_rename_project,
    refactor_rename_project_bowler,
    refactor_rename_rope,
    refactor_rename_symbol,
)


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------

def ok(msg_id: int | None, data: dict[str, Any]) -> dict[str, Any]:
    """Create a JSON-RPC OK response."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]},
    }


def err(msg_id: int | None, code: int, message: str) -> dict[str, Any]:
    """Create a JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "refactor_rename_symbol",
        "description": "Rename a symbol in a Python file using libcst AST transformation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "old_name": {"type": "string", "description": "Current symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
            },
            "required": ["file", "old_name", "new_name"],
        },
    },
    {
        "name": "refactor_rename_symbol_rope",
        "description": "Rename a symbol using rope (supports cross-file renames within project).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "old_name": {"type": "string", "description": "Current symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
                "project_root": {"type": "string", "description": "Project root directory for rope", "default": "."},
            },
            "required": ["file", "old_name", "new_name"],
        },
    },
    {
        "name": "refactor_add_parameter",
        "description": "Add a keyword parameter to matching function calls in a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "func_name": {"type": "string", "description": "Function name to match"},
                "param_name": {"type": "string", "description": "Parameter name to add"},
                "param_value": {"type": "string", "description": "Parameter value to set"},
            },
            "required": ["file", "func_name", "param_name", "param_value"],
        },
    },
    {
        "name": "refactor_extract_function",
        "description": "Extract a code block into a new function using rope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "start_line": {"type": "integer", "description": "Start line number (1-based)"},
                "end_line": {"type": "integer", "description": "End line number (1-based, inclusive)"},
                "function_name": {"type": "string", "description": "Name for the new function"},
            },
            "required": ["file", "start_line", "end_line", "function_name"],
        },
    },
    {
        "name": "refactor_rename_project",
        "description": "Rename a symbol across git-tracked codebase files (respects .gitignore).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_name": {"type": "string", "description": "Old symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
                "root_dir": {"type": "string", "description": "Repository root directory", "default": "."},
                "scope": {
                    "type": "string",
                    "enum": ["tracked", "staged", "modified", "all"],
                    "default": "tracked",
                    "description": "File selection scope (tracked=git-tracked only)",
                },
            },
            "required": ["old_name", "new_name"],
        },
    },
    {
        "name": "refactor_rename_project_bowler",
        "description": "Rename across git-tracked files using bowler with git rollback support.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_name": {"type": "string", "description": "Old symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
                "root_dir": {"type": "string", "description": "Repository root directory", "default": "."},
                "scope": {
                    "type": "string",
                    "enum": ["tracked", "staged", "modified", "all"],
                    "default": "tracked",
                    "description": "File selection scope (tracked=git-tracked only)",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "Preview only (True) or apply changes (False)",
                },
            },
            "required": ["old_name", "new_name"],
        },
    },
    {
        "name": "git_list_tracked_files",
        "description": "List all git-tracked Python files in repository (respects .gitignore).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Repository root directory", "default": "."},
            },
        },
    },
    {
        "name": "refactor_health",
        "description": "Check refactoring tool availability (libcst, rope, bowler).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def tools_call_handler(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a refactoring tool call."""
    if name == "refactor_rename_symbol":
        result = refactor_rename_symbol(args["file"], args["old_name"], args["new_name"])
        return _format_result(result)
    
    elif name == "refactor_rename_symbol_rope":
        project_root = args.get("project_root", ".")
        result = refactor_rename_rope(args["file"], args["old_name"], args["new_name"], project_root)
        return _format_result(result)
    
    elif name == "refactor_add_parameter":
        result = refactor_add_parameter(
            args["file"],
            args["func_name"],
            args["param_name"],
            args["param_value"],
        )
        return _format_result(result)
    
    elif name == "refactor_extract_function":
        result = refactor_extract_function(
            args["file"],
            args["start_line"],
            args["end_line"],
            args["function_name"],
        )
        return _format_result(result)
    
    elif name == "refactor_rename_project":
        root_dir = args.get("root_dir", ".")
        scope = args.get("scope", "tracked")
        results = refactor_rename_project(args["old_name"], args["new_name"], root_dir, scope)
        success_count = sum(1 for r in results if r.success)
        error_count = sum(1 for r in results if not r.success)
        return {
            "scope": scope,
            "success": success_count,
            "errors": error_count,
            "total": len(results),
            "details": [
                {
                    "path": r.original_path,
                    "success": r.success,
                    "preview": r.diff_preview,
                    "error": r.error,
                }
                for r in results[:20]  # Limit output
            ],
        }
    
    elif name == "refactor_rename_project_bowler":
        root_dir = args.get("root_dir", ".")
        scope = args.get("scope", "tracked")
        dry_run = args.get("dry_run", True)
        results = refactor_rename_project_bowler(
            args["old_name"], args["new_name"], root_dir, scope, dry_run=dry_run
        )
        success_count = sum(1 for r in results if r.success)
        error_count = sum(1 for r in results if not r.success)
        return {
            "scope": scope,
            "dry_run": dry_run,
            "success": success_count,
            "errors": error_count,
            "total": len(results),
            "details": [
                {
                    "path": r.original_path,
                    "success": r.success,
                    "preview": r.diff_preview,
                    "error": r.error,
                }
                for r in results[:20]  # Limit output
            ],
        }
    
    elif name == "git_list_tracked_files":
        root_dir = args.get("root_dir", ".")
        files = git_list_tracked_files(root_dir)
        return {"file_count": len(files), "files": files[:100]}  # Limit output
    
    elif name == "refactor_health":
        return {
            "libcst_available": HAS_LIBCST,
            "rope_available": HAS_ROPE,
            "bowler_available": HAS_BOWLER,
            "message": "Refactoring tools ready" if (HAS_LIBCST or HAS_ROPE or HAS_BOWLER) else "No refactoring tools installed",
        }
    
    else:
        return {"error": f"Unknown tool: {name}"}


def _format_result(result: RefactorResult) -> dict[str, Any]:
    """Convert a RefactorResult to MCP-compatible format."""
    output = {
        "success": result.success,
        "tool_used": result.tool_used,
        "preview": result.diff_preview,
    }
    if result.error:
        output["error"] = result.error
    if result.new_content:
        output["new_content"] = result.new_content
    return output


# ---------------------------------------------------------------------------
# MCP request handler
# ---------------------------------------------------------------------------

def mcp_handle_request(
    request: dict[str, Any],
    server_name: str = "refactor-mcp",
    server_version: str = "1.0.0",
) -> dict[str, Any] | None:
    """Handle an MCP JSON-RPC request."""
    msg_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": 2024,
                "serverName": server_name,
                "serverVersion": server_version,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "uriChanges": False},
                },
                "instructions": None,
            },
        }
    
    if method == "notifications/initialized":
        return None
    
    if method == "ping":
        return ok(msg_id, {})
    
    if method == "tools/list":
        return ok(msg_id, {"tools": TOOLS})
    
    if method == "tools/call":
        name = params.get("name", "")
        tool_args = params.get("arguments", {})
        result = tools_call_handler(name, tool_args)
        return ok(msg_id, result)
    
    if method == "logging/setLevel":
        return ok(msg_id, {})
    
    if method.startswith("notifications/"):
        return None
    
    return err(msg_id, -32601, f"method_not_found: {method}")


# ---------------------------------------------------------------------------
# Main serve loop
# ---------------------------------------------------------------------------

def serve(stdin=sys.stdin, stdout=sys.stdout):
    """Main MCP serve loop."""
    while True:
        first = stdin.readline()
        if not first:
            return 0
        decoded = first.decode("utf-8-sig", errors="replace").strip()
        if decoded:
            break
    
    if decoded.startswith("{"):
        request = json.loads(decoded)
    else:
        headers: dict[str, str] = {}
        while True:
            line = stdin.readline()
            if not line:
                return 0
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded == "":
                break
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = stdin.read(length)
        request = json.loads(body.decode("utf-8-sig", errors="replace"))
    
    response = mcp_handle_request(request)
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
        stdout.flush()
    
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    serve()