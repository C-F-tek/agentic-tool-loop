#!/usr/bin/env python3
"""Ruff MCP server — Python linter and formatter via Ruff CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_tool_common import find_cli_tool, run_cli_command
from repo_mcp_common import ok, err, tool_content as _tool_content, mcp_handle_request, mcp_serve

SERVER_NAME = "aicarmine_ruff"
SERVER_VERSION = "1.0.0"


def find_ruff() -> str | None:
    """Locate the ruff binary/CLI entry point."""
    return find_cli_tool("ruff")


def run_ruff(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run ruff on the given target path or stdin."""
    ruff_path = find_ruff()
    if not ruff_path:
        return {
            "ok": False,
            "error": "ruff_not_found",
            "message": "Could not locate ruff CLI. Install via: pipx install ruff",
        }

    args = [ruff_path]

    if action == "check":
        args.append("check")
        if kwargs.get("fix"):
            args.append("--fix")
        if kwargs.get("output_format"):
            args.extend(["--output-format", kwargs["output_format"]])
    elif action == "format":
        args.append("format")
        if kwargs.get("write"):
            args.append("--diff")
        else:
            args.append("--execute")

    if kwargs.get("line_length"):
        args.extend(["--line-length", str(kwargs["line_length"])])

    if target:
        cmd = args + [target]
    else:
        cmd = args + ["-"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.cwd()),
        )
        return {
            "ok": True,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": " ".join(cmd),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "message": f"Failed to run ruff: {exc}"}




TOOLS: dict[str, dict[str, Any]] = {
    "check_file": {
        "name": "check_file",
        "description": "Lint a Python file with Ruff (returns diagnostics)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the Python file to check"},
                "fix": {"type": "boolean", "default": False, "description": "Apply auto-fixes if available"},
                "line_length": {"type": "integer", "default": 88, "minimum": 1, "maximum": 200},
            },
            "required": ["file_path"],
        },
    },
    "format_file": {
        "name": "format_file",
        "description": "Format a Python file with Ruff (read-only, returns formatted content)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the Python file to format"},
                "line_length": {"type": "integer", "default": 88, "minimum": 1, "maximum": 200},
            },
            "required": ["file_path"],
        },
    },
    "format_file_write": {
        "name": "format_file_write",
        "description": "Format a Python file with Ruff and write changes back to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the Python file to format"},
                "line_length": {"type": "integer", "default": 88, "minimum": 1, "maximum": 200},
            },
            "required": ["file_path"],
        },
    },
    "format_stdin": {
        "name": "format_stdin",
        "description": "Format Python code from stdin",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Python code content to format"},
                "line_length": {"type": "integer", "default": 88, "minimum": 1, "maximum": 200},
            },
            "required": ["content"],
        },
    },
    "list_rules": {
        "name": "list_rules",
        "description": "List all Ruff lint rules and their descriptions",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    fix = args.get("fix", False)
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_ruff(target, "check", fix=fix, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_ruff(target, "format", write=False, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_ruff(target, "format", write=True, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")

    try:
        ruff_path = find_ruff()
        if not ruff_path:
            return _tool_content({"ok": False, "error": "ruff_not_found"}, is_error=True)

        proc = subprocess.run(
            [ruff_path, "format"],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        return _tool_content(
            {"ok": True, "formatted_output": proc.stdout},
            is_error=False,
        )
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


def handle_list_rules(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        ruff_path = find_ruff()
        if not ruff_path:
            return _tool_content({"ok": False, "error": "ruff_not_found"}, is_error=True)

        proc = subprocess.run(
            [ruff_path, "rule", "--all"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        if proc.returncode == 0:
            return _tool_content({"ok": True, "rules": proc.stdout}, is_error=False)
        return _tool_content({"ok": False, "error": proc.stderr}, is_error=True)
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


HANDLERS = {
    "check_file": handle_check_file,
    "format_file": handle_format_file,
    "format_file_write": handle_format_file_write,
    "format_stdin": handle_format_stdin,
    "list_rules": handle_list_rules,
}


def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    ruff_path = find_ruff()
    return {
        "ok": bool(ruff_path),
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "ruff_cli": ruff_path,
        "cwd": str(root),
        "tools": list(TOOLS.keys()),
    }


def serve() -> int:
    return mcp_serve(
        sys.stdin.buffer,
        sys.stdout.buffer,
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        tools=TOOLS,
        handlers=HANDLERS,
    )


if __name__ == "__main__":
    serve()
