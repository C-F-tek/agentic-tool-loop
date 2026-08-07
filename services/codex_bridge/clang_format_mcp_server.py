#!/usr/bin/env python3
"""Clang-Format MCP server — C/C++/Java/C# formatter via Clang-Format CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_tool_common import find_cli_tool
from repo_mcp_common import ok, err, tool_content as _tool_content, mcp_serve

SERVER_NAME = "aicarmine_clang_format"
SERVER_VERSION = "1.0.0"


def find_clang_format() -> str | None:
    """Locate the clang-format binary/CLI entry point."""
    return find_cli_tool("clang-format")


def run_clang_format(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run clang-format on the given target path or stdin."""
    clang_path = find_clang_format()
    if not clang_path:
        return {
            "ok": False,
            "error": "clang_format_not_found",
            "message": "Could not locate clang-format CLI. Install via: winget install LLVM.LLVM",
        }

    args = [clang_path]

    if action == "check":
        args.append("--dry-run")
        if kwargs.get("werror"):
            args.append("--Werror")
        if kwargs.get("style"):
            args.extend(["--style", kwargs["style"]])
        elif kwargs.get("config"):
            args.extend(["--config", kwargs["config"]])
    elif action == "format":
        if kwargs.get("style"):
            args.extend(["--style", kwargs["style"]])
        elif kwargs.get("config"):
            args.extend(["--config", kwargs["config"]])
        if kwargs.get("assume_filename"):
            args.extend(["--assume-filename", kwargs["assume_filename"]])

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
        return {"ok": False, "error": str(exc), "message": f"Failed to run clang-format: {exc}"}




TOOLS: dict[str, dict[str, Any]] = {
    "check_file": {
        "name": "check_file",
        "description": "Check if a C/C++/Java/C# file conforms to clang-format style (returns diagnostics)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the C/C++/Java/C# file to check"},
                "style": {"type": "string", "default": "LLVM", "description": "Style name (e.g., LLVM, Google, Chromium)"},
                "config": {"type": "string", "description": "Custom YAML config file path"},
            },
            "required": ["file_path"],
        },
    },
    "format_file": {
        "name": "format_file",
        "description": "Format a C/C++/Java/C# file with Clang-Format (read-only, returns formatted content)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the C/C++/Java/C# file to format"},
                "style": {"type": "string", "default": "LLVM", "description": "Style name (e.g., LLVM, Google, Chromium)"},
                "config": {"type": "string", "description": "Custom YAML config file path"},
            },
            "required": ["file_path"],
        },
    },
    "format_file_write": {
        "name": "format_file_write",
        "description": "Format a C/C++/Java/C# file with Clang-Format and write changes back to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the C/C++/Java/C# file to format"},
                "style": {"type": "string", "default": "LLVM", "description": "Style name (e.g., LLVM, Google, Chromium)"},
                "config": {"type": "string", "description": "Custom YAML config file path"},
            },
            "required": ["file_path"],
        },
    },
    "format_stdin": {
        "name": "format_stdin",
        "description": "Format C/C++/Java/C# code from stdin",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Code content to format"},
                "style": {"type": "string", "default": "LLVM", "description": "Style name (e.g., LLVM, Google, Chromium)"},
                "config": {"type": "string", "description": "Custom YAML config file path"},
            },
            "required": ["content"],
        },
    },
}


def handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    style = args.get("style", "LLVM")
    config = args.get("config")

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_clang_format(target, "check", style=style, config=config)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    style = args.get("style", "LLVM")
    config = args.get("config")

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_clang_format(target, "format", style=style, config=config)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    style = args.get("style", "LLVM")
    config = args.get("config")

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_clang_format(target, "format", style=style, config=config)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")
    style = args.get("style", "LLVM")
    config = args.get("config")

    try:
        clang_path = find_clang_format()
        if not clang_path:
            return _tool_content({"ok": False, "error": "clang_format_not_found"}, is_error=True)

        cmd_args = [clang_path]
        if style:
            cmd_args.extend(["--style", style])
        if config:
            cmd_args.extend(["--config", config])
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
