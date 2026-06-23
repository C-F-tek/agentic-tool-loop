#!/usr/bin/env python3
"""Black MCP server — Python code formatter via Black CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "aicarmine_black"
SERVER_VERSION = "1.0.0"


def _find_black() -> str | None:
    """Locate the black binary/CLI entry point."""
    candidates = [
        "black",
        str(Path.home() / ".local" / "bin" / "black.exe"),
        str(Path.home() / ".local" / "bin" / "black"),
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


def _run_black(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run black on the given target path or stdin."""
    black_path = _find_black()
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


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}], "isError": is_error}


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


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


def _handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    diff = args.get("diff", False)
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = _run_black(target, "check", diff=diff, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def _handle_format_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = _run_black(target, "format", write=False, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def _handle_format_file_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    line_length = args.get("line_length", 88)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = _run_black(target, "format", write=True, line_length=line_length)
    return _tool_content(result, is_error=not result.get("ok"))


def _handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")
    line_length = args.get("line_length", 88)

    try:
        black_path = _find_black()
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
    "check_file": _handle_check_file,
    "format_file": _handle_format_file,
    "format_file_write": _handle_format_file_write,
    "format_stdin": _handle_format_stdin,
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
        return _ok(msg_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": server_name, "version": server_version}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _ok(msg_id, {"tools": [{"name": v["name"], "description": v["description"], "inputSchema": v["inputSchema"]} for v in tools.values()]})
    if method == "tools/call":
        name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = HANDLERS.get(name)
        if handler:
            result = handler(tool_args, root)
            return _ok(msg_id, result)
        return _err(msg_id, -32601, f"unknown_tool: {name}")
    if method == "ping":
        return _ok(msg_id, {})
    return _err(msg_id, -32601, f"method_not_found: {method}")


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