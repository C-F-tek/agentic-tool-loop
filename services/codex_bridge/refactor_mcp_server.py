#!/usr/bin/env python3
"""
MCP server for Python refactoring operations.
Wraps libcst and rope refactoring tools as MCP-compatible operations.

Uses repo_mcp_common.serve() for proper MCP stdio transport.
"""
import sys
from pathlib import Path

# Add the codex_bridge directory to path so repo_mcp_common can be found
_codex_dir = str(Path(__file__).resolve().parent)
if _codex_dir not in sys.path:
    sys.path.insert(0, _codex_dir)

# Add services/ to path for refactor_tools
_services_dir = str(Path(__file__).resolve().parent.parent)
if _services_dir not in sys.path:
    sys.path.insert(0, _services_dir)

# Import our refactor tools
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

# Import the shared serve and helpers
from repo_mcp_common import ToolSpec, serve as mcp_serve

SERVER_NAME = "aicarmine-refactor-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _tool_refactor_rename_symbol(args: dict, repo_root: Path) -> dict:
    file_path = args.get("file", "")
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    if not file_path or not old_name or not new_name:
        return {"error": "Missing required fields: file, old_name, new_name"}
    result = refactor_rename_symbol(file_path, old_name, new_name)
    output = {"success": result.success, "tool_used": result.tool_used, "preview": result.diff_preview}
    if result.error:
        output["error"] = result.error
    if result.new_content:
        output["new_content"] = result.new_content
    return output


def _tool_refactor_rename_symbol_rope(args: dict, repo_root: Path) -> dict:
    file_path = args.get("file", "")
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    project_root = args.get("project_root", ".")
    if not file_path or not old_name or not new_name:
        return {"error": "Missing required fields: file, old_name, new_name"}
    result = refactor_rename_rope(file_path, old_name, new_name, project_root)
    output = {"success": result.success, "tool_used": result.tool_used, "preview": result.diff_preview}
    if result.error:
        output["error"] = result.error
    if result.new_content:
        output["new_content"] = result.new_content
    return output


def _tool_refactor_add_parameter(args: dict, repo_root: Path) -> dict:
    file_path = args.get("file", "")
    func_name = args.get("func_name", "")
    param_name = args.get("param_name", "")
    param_value = args.get("param_value", "")
    if not file_path or not func_name or not param_name or not param_value:
        return {"error": "Missing required fields: file, func_name, param_name, param_value"}
    result = refactor_add_parameter(file_path, func_name, param_name, param_value)
    output = {"success": result.success, "tool_used": result.tool_used, "preview": result.diff_preview}
    if result.error:
        output["error"] = result.error
    if result.new_content:
        output["new_content"] = result.new_content
    return output


def _tool_refactor_extract_function(args: dict, repo_root: Path) -> dict:
    file_path = args.get("file", "")
    start_line = args.get("start_line", 0)
    end_line = args.get("end_line", 0)
    function_name = args.get("function_name", "")
    if not file_path or not start_line or not end_line or not function_name:
        return {"error": "Missing required fields: file, start_line, end_line, function_name"}
    result = refactor_extract_function(file_path, start_line, end_line, function_name)
    output = {"success": result.success, "tool_used": result.tool_used, "preview": result.diff_preview}
    if result.error:
        output["error"] = result.error
    if result.new_content:
        output["new_content"] = result.new_content
    return output


def _tool_refactor_rename_project(args: dict, repo_root: Path) -> dict:
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    root_dir = args.get("root_dir", ".")
    scope = args.get("scope", "tracked")
    if not old_name or not new_name:
        return {"error": "Missing required fields: old_name, new_name"}
    results = refactor_rename_project(old_name, new_name, root_dir, scope)
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
            for r in results[:20]
        ],
    }


def _tool_refactor_rename_project_bowler(args: dict, repo_root: Path) -> dict:
    old_name = args.get("old_name", "")
    new_name = args.get("new_name", "")
    root_dir = args.get("root_dir", ".")
    scope = args.get("scope", "tracked")
    dry_run = args.get("dry_run", True)
    if not old_name or not new_name:
        return {"error": "Missing required fields: old_name, new_name"}
    results = refactor_rename_project_bowler(old_name, new_name, root_dir, scope, dry_run=dry_run)
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
            for r in results[:20]
        ],
    }


def _tool_git_list_tracked_files(args: dict, repo_root: Path) -> dict:
    root_dir = args.get("root_dir", ".")
    files = git_list_tracked_files(root_dir)
    return {"file_count": len(files), "files": files[:100]}


def _tool_refactor_health(args: dict, repo_root: Path) -> dict:
    return {
        "libcst_available": HAS_LIBCST,
        "rope_available": HAS_ROPE,
        "bowler_available": HAS_BOWLER,
        "message": "Refactoring tools ready" if (HAS_LIBCST or HAS_ROPE or HAS_BOWLER) else "No refactoring tools installed",
    }


# Tool registry for repo_mcp_common
TOOLS = {
    "refactor_rename_symbol": ToolSpec(
        name="refactor_rename_symbol",
        description="Rename a symbol in a Python file using libcst AST transformation.",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "old_name": {"type": "string", "description": "Current symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
            },
            "required": ["file", "old_name", "new_name"],
        },
        handler=lambda args, root: _tool_refactor_rename_symbol(args, root),
    ),
    "refactor_rename_symbol_rope": ToolSpec(
        name="refactor_rename_symbol_rope",
        description="Rename a symbol using rope (supports cross-file renames within project).",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "old_name": {"type": "string", "description": "Current symbol name"},
                "new_name": {"type": "string", "description": "New symbol name"},
                "project_root": {"type": "string", "description": "Project root directory for rope", "default": "."},
            },
            "required": ["file", "old_name", "new_name"],
        },
        handler=lambda args, root: _tool_refactor_rename_symbol_rope(args, root),
    ),
    "refactor_add_parameter": ToolSpec(
        name="refactor_add_parameter",
        description="Add a keyword parameter to matching function calls in a file.",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "func_name": {"type": "string", "description": "Function name to match"},
                "param_name": {"type": "string", "description": "Parameter name to add"},
                "param_value": {"type": "string", "description": "Parameter value to set"},
            },
            "required": ["file", "func_name", "param_name", "param_value"],
        },
        handler=lambda args, root: _tool_refactor_add_parameter(args, root),
    ),
    "refactor_extract_function": ToolSpec(
        name="refactor_extract_function",
        description="Extract a code block into a new function using rope.",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the Python file"},
                "start_line": {"type": "integer", "description": "Start line number (1-based)"},
                "end_line": {"type": "integer", "description": "End line number (1-based, inclusive)"},
                "function_name": {"type": "string", "description": "Name for the new function"},
            },
            "required": ["file", "start_line", "end_line", "function_name"],
        },
        handler=lambda args, root: _tool_refactor_extract_function(args, root),
    ),
    "refactor_rename_project": ToolSpec(
        name="refactor_rename_project",
        description="Rename a symbol across git-tracked codebase files (respects .gitignore).",
        input_schema={
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
        handler=lambda args, root: _tool_refactor_rename_project(args, root),
    ),
    "refactor_rename_project_bowler": ToolSpec(
        name="refactor_rename_project_bowler",
        description="Rename across git-tracked files using bowler with git rollback support.",
        input_schema={
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
        handler=lambda args, root: _tool_refactor_rename_project_bowler(args, root),
    ),
    "git_list_tracked_files": ToolSpec(
        name="git_list_tracked_files",
        description="List all git-tracked Python files in repository (respects .gitignore).",
        input_schema={
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Repository root directory", "default": "."},
            },
        },
        handler=lambda args, root: _tool_git_list_tracked_files(args, root),
    ),
    "refactor_health": ToolSpec(
        name="refactor_health",
        description="Check refactoring tool availability (libcst, rope, bowler).",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args, root: _tool_refactor_health(args, root),
    ),
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(mcp_serve(SERVER_NAME, SERVER_VERSION, TOOLS))