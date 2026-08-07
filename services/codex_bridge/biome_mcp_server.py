#!/usr/bin/env python3
"""Biome MCP server — JS/TS formatter and linter via Biome CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_tool_common import find_cli_tool
from repo_mcp_common import ok, err, tool_content as _tool_content, mcp_serve

SERVER_NAME = "aicarmine_biome"
SERVER_VERSION = "1.0.0"


def find_biome() -> str | None:
    """Locate the biome binary/CLI entry point."""
    return find_cli_tool("biome")


def run_biome(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run biome on the given target path or stdin."""
    biome_path = find_biome()
    if not biome_path:
        return {
            "ok": False,
            "error": "biome_not_found",
            "message": "Could not locate biome CLI. Install via: npm install -g @biomejs/biome",
        }

    args = [biome_path]

    if action == "check":
        args.extend(["check", "--write"]) if kwargs.get("fix") else args.append("--verbose")
    elif action == "format":
        args.append("format")
        if kwargs.get("write"):
            args.append("--write")

    if kwargs.get("parser"):
        args.extend(["--parser", kwargs["parser"]])

    if kwargs.get("indent_style"):
        args.extend(["--indent-style", kwargs["indent_style"]])

    if kwargs.get("indent_width"):
        args.extend(["--indent-width", str(kwargs["indent_width"])])

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
        if proc.returncode != 0 and not (proc.returncode == 1 and action == "check" and not kwargs.get("fix")):
            return {
                "ok": False,
                "error": "biome_failed",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "message": f"Biome exited with code {proc.returncode}",
            }
        return {
            "ok": True,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": " ".join(cmd),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "message": f"Failed to run biome: {exc}"}




TOOLS: dict[str, dict[str, Any]] = {
    "format_file": {
        "name": "format_file",
        "description": "Format a JS/TS/JSON/CSS file with Biome (read-only, returns formatted content)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to format"},
                "indent_style": {"type": "string", "enum": ["tab", "space"], "default": "space"},
                "indent_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 4},
            },
            "required": ["file_path"],
        },
    },
    "format_file_write": {
        "name": "format_file_write",
        "description": "Format a JS/TS/JSON/CSS file with Biome and write changes back to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to format"},
                "indent_style": {"type": "string", "enum": ["tab", "space"], "default": "space"},
                "indent_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 4},
            },
            "required": ["file_path"],
        },
    },
    "check_file": {
        "name": "check_file",
        "description": "Lint and check a JS/TS/JSON/CSS file for errors (returns diagnostics)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to check"},
                "fix": {"type": "boolean", "default": False, "description": "Apply auto-fixes if available"},
            },
            "required": ["file_path"],
        },
    },
    "format_stdin": {
        "name": "format_stdin",
        "description": "Format JS/TS code from stdin",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Code content to format"},
                "indent_style": {"type": "string", "enum": ["tab", "space"], "default": "space"},
                "indent_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 4},
            },
            "required": ["content"],
        },
    },
    "list_supported_file_types": {
        "name": "list_supported_file_types",
        "description": "List all supported Biome file types and extensions",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    indent_style = args.get("indent_style", "space")
    indent_width = args.get("indent_width", 2)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_biome(target, "format", write=False, indent_style=indent_style, indent_width=indent_width)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    indent_style = args.get("indent_style", "space")
    indent_width = args.get("indent_width", 2)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_biome(target, "format", write=True, indent_style=indent_style, indent_width=indent_width)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    fix = args.get("fix", False)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_biome(target, "check", fix=fix)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")
    indent_style = args.get("indent_style", "space")
    indent_width = args.get("indent_width", 2)

    try:
        biome_path = find_biome()
        if not biome_path:
            return _tool_content({"ok": False, "error": "biome_not_found"}, is_error=True)

        proc = subprocess.run(
            [biome_path, "format", f"--indent-style={indent_style}", f"--indent-width={indent_width}"],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        if proc.returncode != 0:
            return _tool_content(
                {"ok": False, "error": "biome_failed", "stdout": proc.stdout, "stderr": proc.stderr},
                is_error=True,
            )
        return _tool_content({"ok": True, "formatted_output": proc.stdout}, is_error=False)
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


def handle_list_types(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_types = {
        "JavaScript": ".js",
        "TypeScript": ".ts, .tsx, .cts, .mts",
        "JSON": ".json, .jsonc",
        "CSS": ".css, .scss, .less, .sass",
        "HTML": ".html (via separate tool)",
    }
    return _tool_content({"ok": True, "file_types": file_types}, is_error=False)


HANDLERS = {
    "format_file": handle_format_file,
    "format_file_write": handle_format_file_write,
    "check_file": handle_check_file,
    "format_stdin": handle_format_stdin,
    "list_supported_file_types": handle_list_types,
}


def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    biome_path = find_biome()
    return {
        "ok": bool(biome_path),
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "biome_cli": biome_path,
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
