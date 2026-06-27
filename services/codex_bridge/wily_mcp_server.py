#!/usr/bin/env python3
"""Wily code complexity MCP server — wraps wily CLI for MCP tool calls.

Tools:
- wily_health: Report wily installation, cache status, revision count
- wily_report: Show metrics for a given file
- wily_rank: Rank files/functions by any metric
- wily_build: Build/rebuild wily cache (delta/full)
- wily_index: Show history archive from .wily/ folder
- wily_diff: Show metric differences between revisions
- wily_list_metrics: List available complexity metrics
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    integer_prop,
    object_schema,
    serve,
    string_array_prop,
)

SERVER_NAME = "aicarmine-wily-mcp"
SERVER_VERSION = "0.1.0-incubator"

# Wily is installed in the services/.venv/ virtual environment
_WILY_EXE: str | None = None


def _find_wily_exe() -> str:
    """Find wily executable — try venv first, then PATH."""
    global _WILY_EXE
    if _WILY_EXE is not None:
        return _WILY_EXE

    candidates = [
        str(Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "wily.exe"),
        str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "wily"),
    ]

    for candidate in candidates:
        if Path(candidate).is_file():
            _WILY_EXE = candidate
            return _WILY_EXE

    # Fall back to PATH
    _WILY_EXE = shutil.which("wily") or shutil.which("wily.exe") or ""
    return _WILY_EXE


def _wily_cache_dir() -> str:
    """Return the path to the Wily cache directory."""
    home = os.environ.get("HOME", str(Path.home()))
    return os.path.join(home, ".wily")


def _run_wily(args: list[str], timeout_seconds: int = 60) -> dict[str, Any]:
    """Run a wily CLI command and return structured result."""
    wily_exe = _find_wily_exe()
    if not wily_exe:
        return {"ok": False, "error": "wily_not_found", "data": None}

    try:
        proc = subprocess.run(
            [wily_exe] + args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr[-2000:],
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "wily_timeout",
            "timeout_seconds": timeout_seconds,
            "stdout_tail": (exc.stdout or "")[-2000:],
            "stderr_tail": (exc.stderr or "")[-2000:],
        }
    except FileNotFoundError:
        return {"ok": False, "error": "wily_file_not_found", "path": wily_exe}
    except OSError as exc:
        return {"ok": False, "error": "wily_os_error", "message": str(exc)}


def wily_health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Report Wily installation status and cache health."""
    del root
    wily_exe = _find_wily_exe()
    cache_dir = _wily_cache_dir()

    # Check if cache exists and has data
    cache_exists = os.path.isdir(cache_dir)
    revision_count = 0
    if cache_exists:
        try:
            result = _run_wily(["index"])
            if result.get("ok"):
                stdout = result.get("stdout", "")
                # Count revisions from the table (lines with │)
                revision_count = stdout.count("│") // 3
        except Exception:
            pass

    return {
        "ok": bool(wily_exe and cache_exists),
        "tool": "wily_health",
        "mcp_server": SERVER_NAME,
        "wily_path": wily_exe,
        "wily_installed": bool(wily_exe),
        "cache_dir": cache_dir,
        "cache_exists": cache_exists,
        "revision_count": revision_count,
        "operators": ["raw", "halstead", "cyclomatic", "maintainability"],
    }


def wily_report(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Show metrics for a given file."""
    file_path = str(args.get("path", ""))
    if not file_path:
        return {"ok": False, "error": "missing_path", "tool": "wily_report"}

    full_path = str(root / file_path) if not os.path.isabs(file_path) else file_path
    result = _run_wily(["report", full_path])

    return {
        "ok": result.get("ok"),
        "tool": "wily_report",
        "mcp_server": SERVER_NAME,
        "file": full_path,
        "metrics": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def wily_rank(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Rank files/functions by complexity metric."""
    del root
    metric = str(args.get("metric", "cyclomatic"))
    limit = int(args.get("limit", 50))
    result = _run_wily(["rank", "--metric", metric, "--limit", str(limit)])

    return {
        "ok": result.get("ok"),
        "tool": "wily_rank",
        "mcp_server": SERVER_NAME,
        "metric": metric,
        "limit": limit,
        "data": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def wily_build(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Build/rebuild wily cache (delta or full)."""
    del root
    mode = str(args.get("mode", "delta"))
    result = _run_wily(["build"])

    # Parse output for file count and revision count
    stdout = result.get("stdout", "")
    file_count = 0
    revision_count = 0
    for line in stdout.splitlines():
        if "Processing" in line and "|" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    total = int(parts[-1].strip().split("/")[1] if "/" in parts[-1].strip() else "0/0")
                    file_count = max(file_count, total)
                except (ValueError, IndexError):
                    pass

    return {
        "ok": result.get("ok"),
        "tool": "wily_build",
        "mcp_server": SERVER_NAME,
        "mode": mode,
        "file_count": file_count,
        "stdout": stdout[-5000:],
        "stderr": result.get("stderr", ""),
    }


def wily_index(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Show history archive from .wily/ folder."""
    del root
    result = _run_wily(["index"])

    return {
        "ok": result.get("ok"),
        "tool": "wily_index",
        "mcp_server": SERVER_NAME,
        "data": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def wily_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Show metric differences between revisions."""
    del root
    result = _run_wily(["diff"])

    return {
        "ok": result.get("ok"),
        "tool": "wily_diff",
        "mcp_server": SERVER_NAME,
        "data": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def wily_list_metrics(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """List available complexity metrics."""
    del root
    result = _run_wily(["list-metrics"])

    return {
        "ok": result.get("ok"),
        "tool": "wily_list_metrics",
        "mcp_server": SERVER_NAME,
        "metrics": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["tool_groups"] = ["code_complexity"]
        return payload

    tools["wily_health"] = ToolSpec(
        name="wily_health",
        description="Report Wily installation status and cache health.",
        input_schema=object_schema(),
        handler=wily_health,
    )
    tools["wily_report"] = ToolSpec(
        name="wily_report",
        description="Show metrics (raw, halstead, cyclomatic, maintainability) for a given file.",
        input_schema=object_schema({"path": {"type": "string"}}),
        handler=wily_report,
    )
    tools["wily_rank"] = ToolSpec(
        name="wily_rank",
        description="Rank files/functions by complexity metric.",
        input_schema=object_schema({
            "metric": {"type": "string", "default": "cyclomatic"},
            "limit": integer_prop(50, 1, 500),
        }),
        handler=wily_rank,
    )
    tools["wily_build"] = ToolSpec(
        name="wily_build",
        description="Build/rebuild wily cache (delta or full).",
        input_schema=object_schema({
            "mode": {"type": "string", "enum": ["delta", "full"], "default": "delta"},
        }),
        handler=wily_build,
    )
    tools["wily_index"] = ToolSpec(
        name="wily_index",
        description="Show history archive from .wily/ folder.",
        input_schema=object_schema(),
        handler=wily_index,
    )
    tools["wily_diff"] = ToolSpec(
        name="wily_diff",
        description="Show metric differences between revisions.",
        input_schema=object_schema(),
        handler=wily_diff,
    )
    tools["wily_list_metrics"] = ToolSpec(
        name="wily_list_metrics",
        description="List available complexity metrics.",
        input_schema=object_schema(),
        handler=wily_list_metrics,
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())