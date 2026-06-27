#!/usr/bin/env python3
"""Wily code complexity MCP server — wraps wily CLI + AST-based fallback.

Tools:
- wily_health: Report wily installation, cache status, revision count
- wily_report: Show metrics for a given file (via Wily CLI)
- wily_rank: Rank files/functions by any metric (via Wily CLI)
- wily_build: Build/rebuild wily cache (delta/full)
- wily_index: Show history archive from .wily/ folder
- wily_diff: Show metric differences between revisions
- wily_list_metrics: List available complexity metrics
- ast_complexity_report: Full workspace complexity report via Python AST (fallback)
- ast_file_metrics: Metrics for a single file via Python AST
- ast_top_functions: Top N most complex functions across workspace
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List

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


# ==============================================================================
# AST-based complexity analysis (fallback when Wily cannot extract metrics)
# ==============================================================================


@dataclass
class FunctionMetrics:
    name: str
    file_path: str
    line: int
    end_line: int
    num_lines: int
    num_params: int
    num_nesting: int
    num_ifs: int
    num_for_loops: int
    num_while_loops: int
    num_try_blocks: int
    num_awaits: int
    cyclomatic_complexity: int
    has_docstring: bool


@dataclass
class FileMetrics:
    path: str
    total_lines: int
    class_count: int
    function_count: int
    top_level_functions: int
    top_level_classes: int
    has_main_guard: bool
    functions: List[dict]


def _count_cyclomatic_complexity(node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.With):
            complexity += 1
    return complexity


class _NestingCounter(ast.NodeVisitor):
    def __init__(self):
        self.depth = 0

    def visit_ClassDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_FunctionDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_AsyncFunctionDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1


def _count_nesting(func_node: ast.AST) -> int:
    counter = _NestingCounter()
    counter.visit(func_node)
    return counter.depth


class _DecisionCounter(ast.NodeVisitor):
    def __init__(self):
        self.if_count = 0
        self.for_count = 0
        self.while_count = 0
        self.try_count = 0
        self.await_count = 0

    def visit_If(self, node):
        self.if_count += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.for_count += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.while_count += 1
        self.generic_visit(node)

    def visit_Try(self, node):
        self.try_count += 1
        self.generic_visit(node)

    def visit_Await(self, node):
        self.await_count += 1
        self.generic_visit(node)


def _analyze_function(func_node: ast.AST, file_path: str) -> FunctionMetrics:
    start_line = func_node.lineno
    end_line = func_node.end_lineno or start_line
    num_lines = end_line - start_line + 1

    params = func_node.args
    num_params = (
        len(params.args)
        + len(params.posonlyargs)
        + len(params.kwonlyargs)
        + (1 if params.vararg else 0)
        + (1 if params.kwarg else 0)
    )

    nesting = _count_nesting(func_node)
    decisions = _DecisionCounter()
    decisions.visit(func_node)
    complexity = _count_cyclomatic_complexity(func_node)

    has_docstring = (
        isinstance(func_node.body[0], ast.Expr)
        and isinstance(func_node.body[0].value, (ast.Constant, ast.Str))
    ) if func_node.body else False

    return FunctionMetrics(
        name=func_node.name,
        file_path=file_path,
        line=start_line,
        end_line=end_line,
        num_lines=num_lines,
        num_params=num_params,
        num_nesting=nesting,
        num_ifs=decisions.if_count,
        num_for_loops=decisions.for_count,
        num_while_loops=decisions.while_count,
        num_try_blocks=decisions.try_count,
        num_awaits=decisions.await_count,
        cyclomatic_complexity=complexity,
        has_docstring=has_docstring,
    )


def _analyze_file(file_path: str) -> FileMetrics:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception:
        return None

    lines = source.splitlines()
    total_lines = len(lines)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return None

    classes = [
        node for node in ast.iter_child_nodes(tree) if isinstance(node, ast.ClassDef)
    ]
    functions = [
        node
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    top_level_functions = len(functions)
    top_level_classes = len(classes)

    has_main_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in ast.iter_child_nodes(tree)
    )

    func_metrics = []
    for func_node in functions:
        metrics = _analyze_function(func_node, file_path)
        if metrics:
            func_metrics.append(asdict(metrics))

    return FileMetrics(
        path=file_path,
        total_lines=total_lines,
        class_count=len(classes),
        function_count=top_level_functions,
        top_level_functions=top_level_functions,
        top_level_classes=top_level_classes,
        has_main_guard=has_main_guard,
        functions=func_metrics,
    )


def _walk_python_files(start_dir: str, skip_dirs: list[str] | None = None) -> list[str]:
    """Walk directory tree and collect Python files, skipping unwanted dirs."""
    if skip_dirs is None:
        skip_dirs = [".venv", "__pycache__", "node_modules", ".git"]
    result = []
    for dirpath, dirnames, filenames in os.walk(start_dir):
        # Prune unwanted subdirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not os.path.join(dirpath, d).startswith("..")
        ]
        for filename in filenames:
            if filename.endswith(".py"):
                result.append(os.path.join(dirpath, filename))
    return result


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
    metric = str(args.get("metric", "cyclomatic.complexity"))
    limit = int(args.get("limit", 50))
    # wily rank takes positional args: [PATH] [METRIC] and --limit flag
    result = _run_wily(["rank", ".", metric, "--limit", str(limit)])

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
    mode = str(args.get("mode", "full"))

    # Build from services directory using filesystem archiver
    services_dir = str(Path(__file__).resolve().parent.parent)
    args_list = ["build", "-a", "filesystem", "-o", "cyclomatic,maintainability,raw,halstead"]

    if mode == "full":
        args_list.append("--max-revisions")
        args_list.append("1")

    # Add target files/dirs
    args_list.append("services")

    result = _run_wily(args_list)

    # Parse output for file count and revision count
    stdout = result.get("stdout", "")
    file_count = 0
    revision_count = 0
    for line in stdout.splitlines():
        if "Found" in line and "revisions" in line:
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.isdigit():
                        revision_count = max(revision_count, int(p))
            except (ValueError, IndexError):
                pass

    return {
        "ok": result.get("ok"),
        "tool": "wily_build",
        "mcp_server": SERVER_NAME,
        "mode": mode,
        "file_count": file_count,
        "revision_count": revision_count,
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


# ==============================================================================
# AST-based tools (MCP-integrated fallback)
# ==============================================================================


def ast_complexity_report(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Full workspace complexity report via Python AST.

    Scans all Python files in the workspace root, skipping .venv, __pycache__,
    node_modules, .git directories. Returns file metrics and top functions.
    """
    del args
    workspace_root = str(root)
    python_files = _walk_python_files(workspace_root)
    print(f"AST scanning {len(python_files)} Python files...")

    all_files = []
    for file_path in python_files:
        metrics = _analyze_file(file_path)
        if metrics:
            all_files.append(asdict(metrics))

    # Sort by total lines descending
    all_files.sort(key=lambda x: x["total_lines"], reverse=True)

    # Collect all functions across files
    all_functions = []
    for file_metrics in all_files:
        for func in file_metrics.get("functions", []):
            func["file_path"] = file_metrics["path"]
            all_functions.append(func)

    # Sort functions by cyclomatic complexity descending
    all_functions.sort(key=lambda x: x["cyclomatic_complexity"], reverse=True)

    report = {
        "generated_at": "now",
        "root_directory": workspace_root,
        "total_files": len(all_files),
        "total_functions": len(all_functions),
        "files_by_size": all_files[:50],
        "top_functions_by_complexity": all_functions[:100],
        "summary": {
            "largest_file": all_files[0]["path"] if all_files else None,
            "largest_file_lines": all_files[0]["total_lines"] if all_files else 0,
            "highest_complexity_function": (
                all_functions[0]["name"]
                + " in "
                + all_functions[0]["file_path"]
                if all_functions
                else None
            ),
            "highest_complexity_value": all_functions[0]["cyclomatic_complexity"]
            if all_functions
            else 0,
        },
    }

    return {
        "ok": True,
        "tool": "ast_complexity_report",
        "mcp_server": SERVER_NAME,
        "report": report,
    }


def ast_file_metrics(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Metrics for a single file via Python AST.

    Returns class count, function count, line count, and per-function metrics.
    """
    file_path = str(args.get("path", ""))
    if not file_path:
        return {"ok": False, "error": "missing_path", "tool": "ast_file_metrics"}

    full_path = str(root / file_path) if not os.path.isabs(file_path) else file_path
    metrics = _analyze_file(full_path)

    if metrics is None:
        return {
            "ok": False,
            "error": "file_not_found_or_parse_error",
            "tool": "ast_file_metrics",
        }

    return {
        "ok": True,
        "tool": "ast_file_metrics",
        "mcp_server": SERVER_NAME,
        "file": full_path,
        "metrics": asdict(metrics),
    }


def ast_top_functions(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Top N most complex functions across the workspace via Python AST.

    Args:
        limit: Number of top functions to return (default 50)
        min_complexity: Minimum cyclomatic complexity threshold (default 1)
    """
    limit = int(args.get("limit", 50))
    min_complexity = int(args.get("min_complexity", 1))

    workspace_root = str(root)
    python_files = _walk_python_files(workspace_root)
    print(f"AST scanning {len(python_files)} Python files for top functions...")

    all_functions = []
    for file_path in python_files:
        metrics = _analyze_file(file_path)
        if metrics:
            for func in metrics.functions:
                func["file_path"] = metrics.path
                if func["cyclomatic_complexity"] >= min_complexity:
                    all_functions.append(func)

    # Sort by cyclomatic complexity descending and limit
    all_functions.sort(key=lambda x: x["cyclomatic_complexity"], reverse=True)
    top = all_functions[:limit]

    return {
        "ok": True,
        "tool": "ast_top_functions",
        "mcp_server": SERVER_NAME,
        "total_functions_found": len(all_functions),
        "limit": limit,
        "min_complexity": min_complexity,
        "functions": top,
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

    # AST-based tools (workspace-wide fallback)
    tools["ast_complexity_report"] = ToolSpec(
        name="ast_complexity_report",
        description=(
            "Full workspace complexity report via Python AST. Scans all Python files "
            "in the workspace root, skipping .venv/__pycache__/node_modules/.git. "
            "Returns file metrics and top functions by cyclomatic complexity."
        ),
        input_schema=object_schema(),
        handler=ast_complexity_report,
    )
    tools["ast_file_metrics"] = ToolSpec(
        name="ast_file_metrics",
        description=(
            "Metrics for a single file via Python AST. Returns class count, function "
            "count, line count, and per-function metrics (complexity, nesting, params)."
        ),
        input_schema=object_schema({"path": {"type": "string"}}),
        handler=ast_file_metrics,
    )
    tools["ast_top_functions"] = ToolSpec(
        name="ast_top_functions",
        description=(
            "Top N most complex functions across the workspace via Python AST. "
            "Args: limit (default 50), min_complexity (default 1)."
        ),
        input_schema=object_schema({
            "limit": integer_prop(50, 1, 500),
            "min_complexity": integer_prop(1, 1, 1000),
        }),
        handler=ast_top_functions,
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())