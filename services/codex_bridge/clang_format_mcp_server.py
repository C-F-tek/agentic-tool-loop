#!/usr/bin/env python3
"""Clang-Format MCP server — C/C++/Java/C# formatter via Clang-Format CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import ok, err, tool_content as _tool_content

SERVER_NAME = "aicarmine_clang_format"
SERVER_VERSION = "1.0.0"


def find_clang_format() -> str | None:
    """Locate the clang-format binary/CLI entry point."""
    candidates = [
        "clang-format",
        str(Path("C:/Program Files/LLVM/bin/clang-format.exe")),
        str(Path.home() / ".local" / "bin" / "clang-format.exe"),
        str(Path.home() / ".local" / "bin" / "clang-format"),
    ]
    for candidate in candidates:
        try:
            result = subprocess.run(
                ["where" if sys.platform == "win32" else "which", candidate],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            continue
    return None


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


def handle_request(
    request: dict[str, Any],
    *,
    server_name: str,
    server_version: str,
    tools: dict[str, dict[str, Any]],
    root: Path,
) -> dict[str, Any] | None:
    method = str(request.get("method") or "")
    msg_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return ok(msg_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": server_name, "version": server_version}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok(msg_id, {"tools": [{"name": v["name"], "description": v["description"], "inputSchema": v["inputSchema"]} for v in tools.values()]})
    if method == "tools/call":
        name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = HANDLERS.get(name)
        if handler:
            result = handler(tool_args, root)
            return ok(msg_id, result)
        return err(msg_id, -32601, f"unknown_tool: {name}")
    if method == "ping":
        return ok(msg_id, {})
    return err(msg_id, -32601, f"method_not_found: {method}")


def serve() -> int:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

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

    response = handle_request(
        request,
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        tools=TOOLS,
        root=Path.cwd(),
    )
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stdout.write(raw)
        stdout.flush()


if __name__ == "__main__":
    serve()
