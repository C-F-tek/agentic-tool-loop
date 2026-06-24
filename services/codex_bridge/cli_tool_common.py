#!/usr/bin/env python3
"""Unified CLI tool infrastructure for MCP servers.

Replaces duplicate find_*() and run_*() functions across 6+ MCP servers:
- ruff_mcp_server.py
- black_mcp_server.py
- prettier_mcp_server.py
- biome_mcp_server.py
- eslint_mcp_server.py
- clang_format_mcp_server.py

Usage:
    from cli_tool_common import find_cli_tool, run_cli_command

    # Find binary
    binary = find_cli_tool("ruff", candidates=["ruff", "~/.local/bin/ruff"])

    # Run command
    result = run_cli_command(binary, ["check", "--fix"], target="src/main.py")
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def find_cli_tool(name: str, candidates: list[str] | None = None) -> str | None:
    """Locate a CLI binary/entry point by trying candidate paths.

    Args:
        name: Binary name (e.g., "ruff", "black", "prettier")
        candidates: Optional list of candidate paths. If None, uses defaults.

    Returns:
        Absolute path to the binary, or None if not found.
    """
    if candidates is None:
        home = Path.home()
        candidates = [
            name,
            str(home / ".local" / "bin" / f"{name}.exe"),
            str(home / ".local" / "bin" / name),
        ]

    is_win = sys.platform == "win32"
    search_cmd = "where" if is_win else "which"

    for candidate in candidates:
        try:
            result = subprocess.run(
                [search_cmd, candidate],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            continue

    return None


def run_cli_command(
    binary: str,
    action_args: list[str],
    *,
    target: str | None = None,
    timeout: int = 30,
    **extra_args: Any,
) -> dict[str, Any]:
    """Run a CLI command with unified error handling.

    Args:
        binary: Path to the binary (e.g., "/usr/bin/ruff")
        action_args: Action-specific arguments (e.g., ["check", "--fix"])
        target: Optional file/directory target. If None, reads from stdin.
        timeout: Command timeout in seconds.
        **extra_args: Additional arguments to append.

    Returns:
        Dict with ok, stdout, stderr, returncode keys.
    """
    if not binary:
        return {
            "ok": False,
            "error": "binary_not_found",
            "message": f"Could not locate {binary} CLI.",
        }

    cmd = [binary, *action_args]

    # Add extra args
    for key, value in extra_args.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
        elif isinstance(value, str):
            cmd.extend([flag, value])
        elif isinstance(value, (int, float)):
            cmd.extend([flag, str(value)])

    # Add target or stdin marker
    if target:
        cmd.append(target)
    else:
        cmd.append("-")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.cwd()),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "timeout",
            "message": f"Command timed out after {timeout}s",
            "stdout": exc.stdout if hasattr(exc, "stdout") else "",
            "stderr": exc.stderr if hasattr(exc, "stderr") else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "message": f"Command failed: {type(exc).__name__}",
        }


# ── Legacy compatibility aliases (for servers that still use find_* / run_*) ──

def find_tool(name: str) -> str | None:
    """Alias for find_cli_tool — kept for backward compatibility."""
    return find_cli_tool(name)


def run_tool(binary: str, action_args: list[str], **kwargs: Any) -> dict[str, Any]:
    """Alias for run_cli_command — kept for backward compatibility."""
    return run_cli_command(binary, action_args, **kwargs)