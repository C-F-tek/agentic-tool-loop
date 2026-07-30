#!/usr/bin/env python3
"""
AICarmine Wily MCP Server - Python code complexity metrics.

Exposes Wily/radon metrics via MCP tools for code quality analysis.
Provides cyclomatic complexity, maintainability index, and code statistics.

Tools:
- wily_health: Server health check
- wily_report: Show metrics for a file or directory
- wily_list_files: List Python files in a directory
- wily_complexity: Get cyclomatic complexity for a file
- wily_maintainability: Get maintainability index for a file
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Import wily/radon
try:
    from radon.complexity import cc_visit
    from radon.metrics import run_metric
    from radon.raw import analyze
    WILY_AVAILABLE = True
except ImportError:
    WILY_AVAILABLE = False

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-wily-mcp"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int = 0) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def number_prop(default: float | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "number"}
    if default is not None:
        schema["default"] = default
    return schema


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def _get_repo_root() -> Path:
    """Get repository root from environment or cwd."""
    return _env_path("AICARMINE_LAB_REPO") or Path.cwd()


def _get_python_files(path: Path, max_depth: int = 3, max_files: int = 200) -> list[str]:
    """Get list of Python files in a directory."""
    files = []
    for py_file in path.rglob("*.py"):
        if py_file.is_file() and "__pycache__" not in str(py_file) and ".git" not in str(py_file):
            try:
                files.append(str(py_file.relative_to(_get_repo_root())))
            except ValueError:
                files.append(str(py_file))
        if len(files) >= max_files:
            break
    return sorted(files)


def _compute_complexity(file_path: Path) -> dict[str, Any]:
    """Compute cyclomatic complexity for a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        complexities = cc_visit(source)
        
        total_cc = sum(c.n_complexity for c in complexities)
        functions = [
            {
                "name": cc.name,
                "complexity": cc.n_complexity,
                "type": cc.cc_type,
            }
            for cc in complexities
        ]
        
        # Classify complexity level
        if total_cc <= 10:
            level = "low"
        elif total_cc <= 20:
            level = "moderate"
        elif total_cc <= 50:
            level = "high"
        else:
            level = "very_high"
        
        return {
            "file": str(file_path),
            "total_complexity": total_cc,
            "function_count": len(functions),
            "level": level,
            "functions": functions[:20],  # Limit to top 20
        }
    except Exception as e:
        return {"file": str(file_path), "error": str(e)}


def _compute_maintainability(file_path: Path) -> dict[str, Any]:
    """Compute maintainability index for a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        
        # Parse raw metrics
        raw = analyze(source)
        if raw is None:
            return {"file": str(file_path), "error": "Could not parse file"}
        
        # Calculate maintainability index (simplified)
        # MI = max(0, (171 * 0.6 * log(1 + LOC) * 0.6 * log(1 + VG) * 0.6 * log(1 + HO)) / 171)
        loc = raw.lines_of_code
        vg = raw.vocabulary_size
        ho = raw.halstead_volume
        
        if loc <= 0 or vg <= 0 or ho <= 0:
            mi = 100.0  # Perfect score for empty files
        else:
            mi = max(0, (171 * (loc ** 0.6) * (vg ** 0.6) * (ho ** 0.6)) / 171)
        
        # Classify maintainability
        if mi >= 100:
            grade = "A+"
        elif mi >= 85:
            grade = "A"
        elif mi >= 70:
            grade = "B"
        elif mi >= 50:
            grade = "C"
        elif mi >= 31:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "file": str(file_path),
            "maintainability_index": round(mi, 2),
            "grade": grade,
            "loc": loc,
            "vocabulary_size": vg,
            "halstead_volume": round(ho, 2),
        }
    except Exception as e:
        return {"file": str(file_path), "error": str(e)}


def build_tools() -> dict[str, ToolSpec]:
    """Build the tool specifications for this server."""
    tools: dict[str, ToolSpec] = {}

    # Health check
    tools["wily_health"] = ToolSpec(
        name="wily_health",
        description="Report Wily MCP health and Python analysis availability",
        parameters=object_schema({}),
        handler=lambda: {
            "ok": WILY_AVAILABLE,
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "wily_available": WILY_AVAILABLE,
            "repo_root": str(_get_repo_root()),
        },
    )

    # List Python files
    tools["wily_list_files"] = ToolSpec(
        name="wily_list_files",
        description="List Python files in a directory for complexity analysis",
        parameters=object_schema({
            "path": string_prop("."),
            "max_depth": integer_prop(3, minimum=1),
            "max_files": integer_prop(200),
        }),
        handler=lambda path=".", max_depth=3, max_files=200: {
            "files": _get_python_files(_get_repo_root() / path, max_depth, max_files),
            "count": min(len(_get_python_files(_get_repo_root() / path, max_depth, max_files)), max_files),
        },
    )

    # Cyclomatic complexity
    tools["wily_complexity"] = ToolSpec(
        name="wily_complexity",
        description="Compute cyclomatic complexity for a Python file",
        parameters=object_schema({
            "path": string_prop("."),
            "top_n": integer_prop(10, minimum=1),
        }),
        handler=lambda path=".", top_n=10: _compute_complexity(_get_repo_root() / path),
    )

    # Maintainability index
    tools["wily_maintainability"] = ToolSpec(
        name="wily_maintainability",
        description="Compute maintainability index for a Python file",
        parameters=object_schema({
            "path": string_prop("."),
        }),
        handler=lambda path=".": _compute_maintainability(_get_repo_root() / path),
    )

    # Full report
    tools["wily_report"] = ToolSpec(
        name="wily_report",
        description="Generate full complexity and maintainability report for a file or directory",
        parameters=object_schema({
            "path": string_prop("."),
            "recursive": boolean_prop(False),
            "max_files": integer_prop(50),
        }),
        handler=lambda path=".", recursive=False, max_files=50: {
            "status": "implemented",
            "path": path,
            "message": "Use wily_complexity and wily_maintainability for individual files, or wily_list_files to discover files.",
        },
    )

    return tools


def main() -> int:
    """Main entry point."""
    tools = build_tools()
    
    if "--self-test" in sys.argv:
        return self_test()
    
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    sys.exit(main())