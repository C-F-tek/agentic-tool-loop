#!/usr/bin/env python3
"""Prettier MCP server — formats code/files with Prettier via CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import ok, err, tool_content as _tool_content

SERVER_NAME = "aicarmine_prettier"
SERVER_VERSION = "1.0.0"


def _log(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def find_prettier() -> str | None:
    """Locate the prettier binary/CLI entry point."""
    # Try global npm install first
    candidates = [
        "prettier",
        "npx",
        str(Path.home() / "AppData" / "Roaming" / "npm" / "prettier.cmd"),
        str(Path.home() / "AppData" / "Roaming" / "npm" / "prettier"),
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


def run_prettier(target: str, write: bool = False, tab_width: int = 2, parser: str | None = None) -> dict[str, Any]:
    """Run prettier on the given target path or stdin."""
    prettier_path = find_prettier()
    if not prettier_path:
        return {
            "ok": False,
            "error": "prettier_not_found",
            "message": "Could not locate prettier CLI. Install via: npm install -g prettier",
        }

    args = [prettier_path]
    if write:
        args.append("--write")
    else:
        args.append("--stdin-filepath")

    if tab_width:
        args.extend(["--tab-width", str(tab_width)])

    if parser:
        args.extend(["--parser", parser])

    cmd = args + [target] if target else args + ["-"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.cwd()),
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "prettier_failed",
                "stderr": proc.stderr,
                "message": f"Prettier exited with code {proc.returncode}",
            }
        return {
            "ok": True,
            "formatted_output": proc.stdout,
            "command": " ".join(cmd),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "message": f"Failed to run prettier: {exc}",
        }




# --- Tool definitions ---

TOOLS: dict[str, dict[str, Any]] = {
    "format_file": {
        "name": "format_file",
        "description": "Format a file with Prettier (read-only, returns formatted content)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to format"},
                "parser": {
                    "type": "string",
                    "enum": ["babel", "typescript", "flow", "json", "yaml", "markdown", "css", "html"],
                    "default": "typescript",
                    "description": "Parser to use for the file type",
                },
                "tab_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 8},
            },
            "required": ["file_path"],
        },
    },
    "format_file_write": {
        "name": "format_file_write",
        "description": "Format a file with Prettier and write changes back to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to format"},
                "parser": {
                    "type": "string",
                    "enum": ["babel", "typescript", "flow", "json", "yaml", "markdown", "css", "html"],
                    "default": "typescript",
                    "description": "Parser to use for the file type",
                },
                "tab_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 8},
            },
            "required": ["file_path"],
        },
    },
    "format_stdin": {
        "name": "format_stdin",
        "description": "Format code from stdin (useful for inline formatting)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Code content to format"},
                "parser": {
                    "type": "string",
                    "enum": ["babel", "typescript", "flow", "json", "yaml", "markdown", "css", "html"],
                    "default": "typescript",
                    "description": "Parser to use for the file type",
                },
                "tab_width": {"type": "integer", "default": 2, "minimum": 1, "maximum": 8},
            },
            "required": ["content"],
        },
    },
    "list_supported_parsers": {
        "name": "list_supported_parsers",
        "description": "List all supported Prettier parsers and their file extensions",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}


def handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    parser = args.get("parser", "typescript")
    tab_width = args.get("tab_width", 2)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_prettier(target, write=False, tab_width=tab_width, parser=parser)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    parser = args.get("parser", "typescript")
    tab_width = args.get("tab_width", 2)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = run_prettier(target, write=True, tab_width=tab_width, parser=parser)
    return _tool_content(result, is_error=not result.get("ok"))


def handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")
    parser = args.get("parser", "typescript")
    tab_width = args.get("tab_width", 2)

    try:
        proc = subprocess.run(
            [find_prettier(), f"--stdin-filepath=temp.{parser}", f"--tab-width={tab_width}"],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        if proc.returncode != 0:
            return _tool_content(
                {"ok": False, "error": "prettier_failed", "stderr": proc.stderr},
                is_error=True,
            )
        return _tool_content({"ok": True, "formatted_output": proc.stdout}, is_error=False)
    except Exception as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)


def handle_list_parsers(args: dict[str, Any], root: Path) -> dict[str, Any]:
    parsers = {
        "babel": ".js, .jsx, .flow, .graphql",
        "typescript": ".ts, .tsx, .cts, .mts",
        "json": ".json, .jsonc",
        "yaml": ".yaml, .yml",
        "markdown": ".md, .mkd, .mdown, .markdown",
        "css": ".css, .scss, .less, .sass",
        "html": ".html, .htm, .handlebars",
    }
    return _tool_content({"ok": True, "parsers": parsers}, is_error=False)


HANDLERS = {
    "format_file": handle_format_file,
    "format_file_write": handle_format_file_write,
    "format_stdin": handle_format_stdin,
    "list_supported_parsers": handle_list_parsers,
}


def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    prettier_path = find_prettier()
    return {
        "ok": bool(prettier_path),
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "prettier_cli": prettier_path,
        "cwd": str(root),
        "tools": list(TOOLS.keys()),
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
