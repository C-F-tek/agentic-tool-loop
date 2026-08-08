#!/usr/bin/env python3
"""MCP server for performance profiling analysis.

Analyzes Python code for performance issues, detects potential memory leaks,
finds slow query patterns, and provides optimization suggestions.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Add codex_bridge to sys.path for repo_mcp_common import
try:
    _codex_bridge_dir = Path(__file__).resolve().parent
except NameError:
    _codex_bridge_dir = Path("services/codex_bridge").resolve()
if str(_codex_bridge_dir) not in sys.path:
    sys.path.insert(0, str(_codex_bridge_dir))

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-performance-profiler-mcp"
SERVER_VERSION = "1.0.0"


class PerformanceProfiler:
    """Analyzes Python code for performance issues."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    # Performance anti-patterns
    ANTI_PATTERNS: list[tuple[str, str, str, str]] = [
        (
            "list_comprehension_in_loop",
            r'\bfor\s+\w+\s+in\s+.*:\s*\n\s*.*\.append\s*\(',
            "Using .append() in loop instead of list comprehension",
            "medium"
        ),
        (
            "string_concat_in_loop",
            r'\bfor\s+\w+\s+in\s+.*:\s*\n\s*.*\+=\s*',
            "String concatenation in loop (use join instead)",
            "high"
        ),
        (
            "nested_loop",
            r'for\s+.+\s+in\s+.*:\s*\n\s*(.*)for\s+.+\s+in\s+.*:',
            "Nested loops detected - consider optimization",
            "high"
        ),
        (
            "global_variable_usage",
            r'\bglobal\s+',
            "Global variable usage detected",
            "low"
        ),
        (
            "unused_import",
            r'import\s+\w+\s*(?:as\s+\w+)?\s*$',
            "Potential unused import",
            "low"
        ),
        (
            "bare_except",
            r'except\s*:',
            "Bare except clause - specify exception type",
            "medium"
        ),
        (
            "mutable_default_arg",
            r'def\s+\w+\s*\([^)]*(?:=\s*\[\]|=\s*\{\})',
            "Mutable default argument - use None instead",
            "high"
        ),
        (
            "recursive_without_base",
            r'def\s+\w+\s*\([^)]*\):\s*\n\s*.*\w+\s*\(',
            "Potential infinite recursion - check base case",
            "high"
        ),
    ]

    def _find_python_files(self, path: str | None = None) -> list[Path]:
        """Find all Python files."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        return sorted(target.rglob("*.py"), key=lambda p: p.relative_to(self.repo_root))

    def profile(self, path: str = ".", include_timing: bool = False) -> dict[str, Any]:
        """Profile a module for performance characteristics."""
        py_files = self._find_python_files(path)
        results: list[dict[str, Any]] = []
        total_functions = 0
        total_classes = 0
        total_lines = 0

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception:
                continue

            func_count = 0
            class_count = 0
            lines = source.count('\n') + 1

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_count += 1
                    total_functions += 1
                    
                    # Check function complexity
                    complexity = self._calculate_complexity(node)
                    if complexity > 10:
                        results.append({
                            "file": str(pf.relative_to(self.repo_root)),
                            "type": "function",
                            "name": node.name,
                            "issue": f"High cyclomatic complexity: {complexity}",
                            "severity": "medium" if complexity < 20 else "high"
                        })
                elif isinstance(node, ast.ClassDef):
                    class_count += 1
                    total_classes += 1

            total_lines += lines
            results.append({
                "file": str(pf.relative_to(self.repo_root)),
                "functions": func_count,
                "classes": class_count,
                "lines": lines,
                "complexity_score": self._estimate_complexity(tree)
            })

        return {
            "ok": True,
            "path": path,
            "files_profiled": len(py_files),
            "total_functions": total_functions,
            "total_classes": total_classes,
            "total_lines": total_lines,
            "avg_complexity": round(sum(r.get("complexity_score", 0) for r in results) / max(len(results), 1), 2),
            "issues": [r for r in results if "issue" in r][:100],
            "file_stats": results[:200]
        }

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1
        for node in ast.walk(node):
            if isinstance(node, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
        return complexity

    def _estimate_complexity(self, tree: ast.Module) -> int:
        """Estimate overall module complexity."""
        total = 0
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                total += self._calculate_complexity(node)
        return total

    def memory_leak_detector(self, path: str = ".") -> dict[str, Any]:
        """Detect potential memory leaks."""
        py_files = self._find_python_files(path)
        leaks: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception:
                continue

            # Check for unbounded collections
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if 'cache' in target.id.lower() or 'buffer' in target.id.lower():
                                if isinstance(node.value, (ast.List, ast.Dict)):
                                    leaks.append({
                                        "file": str(pf.relative_to(self.repo_root)),
                                        "line": node.lineno,
                                        "type": "unbounded_collection",
                                        "variable": target.id,
                                        "severity": "medium"
                                    })

            # Check for missing context managers
            for node in ast.walk(tree):
                if isinstance(node, ast.With):
                    if not node.items:
                        leaks.append({
                            "file": str(pf.relative_to(self.repo_root)),
                            "line": node.lineno,
                            "type": "missing_context_manager",
                            "severity": "low"
                        })

        return {
            "ok": True,
            "path": path,
            "files_scanned": len(py_files),
            "potential_leaks": len(leaks),
            "leaks": leaks[:100]
        }

    def slow_query_finder(self, path: str = ".") -> dict[str, Any]:
        """Find potential slow database queries."""
        py_files = self._find_python_files(path)
        queries: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
            except Exception:
                continue

            # Check for SQL queries without parameters
            import re
            sql_patterns = [
                (r'(?:SELECT|INSERT|UPDATE|DELETE)\s+.*(?:FROM|INTO|SET)\s+\w+', 'SQL query pattern'),
                (r'cursor\.execute\s*\(\s*["\']', 'Direct SQL execution'),
                (r'execute\s*\(\s*f["\']', 'f-string SQL construction'),
            ]

            for pattern, desc in sql_patterns:
                matches = list(re.finditer(pattern, source, re.IGNORECASE))
                for m in matches:
                    line_num = source[:m.start()].count('\n') + 1
                    lines = source.split('\n')
                    queries.append({
                        "file": str(pf.relative_to(self.repo_root)),
                        "line": line_num,
                        "type": desc,
                        "snippet": lines[line_num - 1].strip()[:200] if line_num <= len(lines) else "",
                        "severity": "high" if 'f"' in lines[line_num - 1] else "medium"
                    })

        return {
            "ok": True,
            "path": path,
            "files_scanned": len(py_files),
            "queries_found": len(queries),
            "queries": queries[:100]
        }

    def optimization_suggestions(self, path: str = ".") -> dict[str, Any]:
        """Generate optimization suggestions."""
        py_files = self._find_python_files(path)
        suggestions: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception:
                continue

            # Check for anti-patterns
            for name, pattern, description, severity in self.ANTI_PATTERNS:
                matches = list(re.finditer(pattern, source))
                if matches:
                    lines = source.split('\n')
                    for m in matches:
                        line_num = source[:m.start()].count('\n') + 1
                        suggestions.append({
                            "file": str(pf.relative_to(self.repo_root)),
                            "line": line_num,
                            "pattern": name,
                            "description": description,
                            "severity": severity,
                            "suggestion": f"Consider refactoring: {description}",
                            "snippet": lines[line_num - 1].strip()[:100] if line_num <= len(lines) else ""
                        })

            # Check for generator usage opportunities
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if 'yield' in source[node.lineno - 1:]:
                        suggestions.append({
                            "file": str(pf.relative_to(self.repo_root)),
                            "function": node.name,
                            "type": "generator_detected",
                            "suggestion": "Function uses yield - good for memory efficiency",
                            "priority": "info"
                        })

        return {
            "ok": True,
            "path": path,
            "files_analyzed": len(py_files),
            "suggestions_count": len(suggestions),
            "high_priority": len([s for s in suggestions if s.get("severity") == "high"]),
            "medium_priority": len([s for s in suggestions if s.get("severity") == "medium"]),
            "suggestions": suggestions[:200]
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_profiler: PerformanceProfiler | None = None

def _get_profiler(repo_root: str) -> PerformanceProfiler:
    global _profiler
    if _profiler is None:
        _profiler = PerformanceProfiler(repo_root)
    return _profiler


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_profile"] = ToolSpec(
        name="aicarmine_profile",
        description="Profile a module for performance characteristics",
        input_schema=object_schema({
            "path": {"type": "string"},
            "include_timing": {"type": "boolean"}
        }),
        handler=lambda args, root: _get_profiler(str(root)).profile(
            path=args.get("path", "."),
            include_timing=args.get("include_timing", False)
        ),
    )

    tools["aicarmine_memory_leak_detector"] = ToolSpec(
        name="aicarmine_memory_leak_detector",
        description="Detect potential memory leaks",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_profiler(str(root)).memory_leak_detector(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_slow_query_finder"] = ToolSpec(
        name="aicarmine_slow_query_finder",
        description="Find potential slow database queries",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_profiler(str(root)).slow_query_finder(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_optimization_suggestions"] = ToolSpec(
        name="aicarmine_optimization_suggestions",
        description="Generate optimization suggestions",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_profiler(str(root)).optimization_suggestions(
            path=args.get("path", ".")
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())