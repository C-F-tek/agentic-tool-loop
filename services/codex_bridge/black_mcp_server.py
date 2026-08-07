#!/usr/bin/env python3
"""Black MCP server — Python code formatter via Black CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_tool_common import find_cli_tool, run_cli_command
from repo_mcp_common import ok, err, tool_content as _tool_content, mcp_serve

SERVER_NAME = "aicarmine_black"
SERVER_VERSION = "1.0.0"


def find_black() -> str | None:
    """Locate the black binary/CLI entry point."""
    return find_cli_tool("black")


def run_black(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run black on the given target path or stdin."""
    black_path = find_black()
    if not black_path:
        return {
            "ok": False,
            "error": "black_not_found",
            "message": "Could not locate black CLI. Install via: pipx install black",
        }

    args = [black_path]

    if action == "check":
        args.append("--check")
        if kwargs.get("diff"):
            args.append("--diff")
    elif action == "format":
        if kwargs.get("write"):
            pass  # default behavior
        else:
            args.append("--quiet")

    if kwargs.get("line_length"):
        args.extend(["--line-length", str(kwargs["line_length"])])
    if kwargs.get("target_version"):
        args.extend(["--target-version", kwargs["target_version"]])

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
        return {"ok": False, "error": str(exc), "message": f"Failed to run black: {exc}"}




TOOLS: dict[str, dict[str, Any]] = {
    "check_file": {
        "name": "check_file",
        "description": "Check if a Python file is formatted by Black (returns diagnostics)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the Python file to check"},
                "diff": {"type": "boolean", "default": False, "description": "Show diff of changes needed"},
                "line_length": {"type": "integer", "default": 88, "minimum": 1, "maximum": 200},
            },
            "required": ["file_path"],
        },
    },
    "format_file": {
        "name": "format_file",
        "description": "Format a Python file with Black (read-only, returns formatted content)",
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
        "description": "Format a Python file with Black and write changes back to disk",
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
}


def handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    diff = args.get("diff", False)
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_black(target, "check", diff=diff, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_black(target, "format", write=False, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_black(target, "format", write=True, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")
    line_length = args.get("line_length", 88)

    try:
        black_path = find_black()
        if not black_path:
            return _tool_content({"ok": False, "error": "black_not_found"}, is_error=True)

        cmd_args = [black_path]
        if line_length:
            cmd_args.extend(["--line-length", str(line_length)])
        cmd_args.append("-")

        proc = subprocess.run(
            cmd_args,
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


HANDLERS = {
    "check_file": handle_check_file,
    "format_file": handle_format_file,
    "format_file_write": handle_format_file_write,
    "format_stdin": handle_format_stdin,
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
