#!/usr/bin/env python3
"""ESLint MCP server — JavaScript/TypeScript linter via ESLint CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_tool_common import find_cli_tool
from repo_mcp_common import ok, err, tool_content as _tool_content, mcp_serve

SERVER_NAME = "aicarmine_eslint"
SERVER_VERSION = "1.0.0"


def find_eslint() -> str | None:
    """Locate the eslint binary/CLI entry point."""
    return find_cli_tool("eslint")


def run_eslint(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run eslint on the given target path or stdin."""
    eslint_path = find_eslint()
    if not eslint_path:
        return {
            "ok": False,
            "error": "eslint_not_found",
            "message": "Could not locate eslint CLI. Install via: npm install -g eslint",
        }

    args = [eslint_path]

    if action == "check":
        args.append("--no-color")
        if kwargs.get("fix"):
            args.append("--fix")
        if kwargs.get("quiet"):
            args.append("--quiet")
        if kwargs.get("format"):
            args.extend(["--format", kwargs["format"]])
        else:
            args.extend(["--format", "json"])
    elif action == "lint":
        args.append("--no-color")
        if kwargs.get("output_format"):
            args.extend(["--format", kwargs["output_format"]])
        else:
            args.extend(["--format", "json"])

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
        return {"ok": False, "error": str(exc), "message": f"Failed to run eslint: {exc}"}




TOOLS: dict[str, dict[str, Any]] = {
    "check_file": {
        "name": "check_file",
        "description": "Lint a JavaScript/TypeScript file with ESLint (returns diagnostics)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the JS/TS file to check"},
                "fix": {"type": "boolean", "default": False, "description": "Apply auto-fixes if available"},
                "quiet": {"type": "boolean", "default": False, "description": "Suppress warnings"},
            },
            "required": ["file_path"],
        },
    },
    "format_stdin": {
        "name": "format_stdin",
        "description": "Lint JavaScript/TypeScript code from stdin",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Code content to lint"},
            },
            "required": ["content"],
        },
    },
    "list_rules": {
        "name": "list_rules",
        "description": "List all ESLint rules and their descriptions",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    fix = args.get("fix", False)
    quiet = args.get("quiet", False)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_eslint(target, "check", fix=fix, quiet=quiet)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")

    try:
        eslint_path = find_eslint()
        if not eslint_path:
            return _tool_content({"ok": False, "error": "eslint_not_found"}, is_error=True)

        proc = subprocess.run(
            [eslint_path, "--no-color", "--format", "json", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        return _tool_content(
            {"ok": True, "exit_code": proc.returncode, "stdout": proc.stdout},
            is_error=False,
        )
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


def handle_list_rules(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        eslint_path = find_eslint()
        if not eslint_path:
            return _tool_content({"ok": False, "error": "eslint_not_found"}, is_error=True)

        proc = subprocess.run(
            [eslint_path, "--print-config"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        return _tool_content(
            {"ok": True, "rules": proc.stdout},
            is_error=False,
        )
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


HANDLERS = {
    "check_file": handle_check_file,
    "format_stdin": handle_format_stdin,
    "list_rules": handle_list_rules,
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
