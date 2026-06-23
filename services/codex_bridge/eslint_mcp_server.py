#!/usr/bin/env python3
"""ESLint MCP server — JavaScript/TypeScript linter via ESLint CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "aicarmine_eslint"
SERVER_VERSION = "1.0.0"


def _find_eslint() -> str | None:
    """Locate the eslint binary/CLI entry point."""
    candidates = [
        "eslint",
        str(Path.home() / "AppData" / "Roaming" / "npm" / "eslint.cmd"),
        str(Path.home() / "AppData" / "Roaming" / "npm" / "eslint.exe"),
        str(Path.home() / "AppData" / "Roaming" / "npm" / "eslint"),
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


def _run_eslint(target: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
    """Run eslint on the given target path or stdin."""
    eslint_path = _find_eslint()
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


def _handle_check_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    file_path = args.get("file_path", "")
    fix = args.get("fix", False)
    quiet = args.get("quiet", False)

    target = str(root / file_path) if not Path(file_path).is_absolute() else file_path
    result = _run_eslint(target, "check", fix=fix, quiet=quiet)
    return _tool_content(result, is_error=not result.get("ok"))


def _handle_format_stdin(args: dict[str, Any], root: Path) -> dict[str, Any]:
    content = args.get("content", "")

    try:
        eslint_path = _find_eslint()
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


def _handle_list_rules(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        eslint_path = _find_eslint()
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
    "check_file": _handle_check_file,
    "format_stdin": _handle_format_stdin,
    "list_rules": _handle_list_rules,
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