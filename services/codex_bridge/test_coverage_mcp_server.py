#!/usr/bin/env python3
"""MCP server for test coverage analysis and discovery.

Analyzes Python test files, measures code coverage gaps, discovers
untested patterns, and generates test scaffolds for uncovered modules.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import threading
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

SERVER_NAME = "aicarmine-test-coverage-mcp"
SERVER_VERSION = "1.0.0"


class TestCoverageAnalyzer:
    """Analyzes test coverage across a Python repository."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}

    def _find_python_files(self, path: str | None = None, include_tests: bool = True) -> list[Path]:
        """Find all Python files in the repository or subdirectory."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        py_files = list(target.rglob("*.py")) if target.is_dir() else [target] if target.suffix == ".py" else []
        if not include_tests:
            py_files = [f for f in py_files if 'test' not in f.name.lower() and 'tests' not in str(f.parent)]
        return sorted(py_files, key=lambda p: p.relative_to(self.repo_root))

    def _find_test_files(self, path: str | None = None) -> list[Path]:
        """Find all test files in the repository."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        test_files = []
        for root, dirs, files in os.walk(str(target)):
            for f in files:
                if f.endswith('_test.py') or f.startswith('test_') and f.endswith('.py'):
                    test_files.append(Path(root) / f)
        return sorted(test_files, key=lambda p: p.relative_to(self.repo_root))

    def _extract_symbols(self, filepath: Path) -> dict[str, Any]:
        """Extract symbols (classes, functions) from a Python file."""
        try:
            source = filepath.read_text(encoding='utf-8')
            tree = ast.parse(source, str(filepath))
        except Exception as e:
            return {"error": str(e), "symbols": [], "lines": 0}

        symbols = []
        lines = source.count('\n') + 1

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "type": "class",
                    "name": node.name,
                    "line": node.lineno,
                    "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                })
            elif isinstance(node, ast.FunctionDef):
                if node.lineno > 0:  # Skip module-level functions at line 0
                    symbols.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "params": [arg.arg for arg in node.args.args]
                    })

        return {"symbols": symbols, "lines": lines}

    def _check_coverage(self, symbol: dict, test_files: list[Path]) -> bool:
        """Check if a symbol is referenced in any test file."""
        if symbol["type"] != "function" and symbol["type"] != "class":
            return False
        name = symbol["name"]
        for tf in test_files:
            try:
                content = tf.read_text(encoding='utf-8')
                if name in content:
                    return True
            except Exception:
                continue
        return False

    def coverage_report(self, path: str = ".", min_coverage: float = 0.0) -> dict[str, Any]:
        """Generate a coverage report for the given path."""
        py_files = self._find_python_files(path, include_tests=False)
        test_files = self._find_test_files(path)
        
        total_symbols = 0
        covered_symbols = 0
        uncovered = []
        file_stats = []

        for pf in py_files:
            result = self._extract_symbols(pf)
            if "error" in result:
                continue
            file_symbols = result.get("symbols", [])
            for sym in file_symbols:
                total_symbols += 1
                if self._check_coverage(sym, test_files):
                    covered_symbols += 1
                else:
                    uncovered.append({
                        "file": str(pf.relative_to(self.repo_root)),
                        "type": sym["type"],
                        "name": sym["name"],
                        "line": sym["line"]
                    })
            file_stats.append({
                "file": str(pf.relative_to(self.repo_root)),
                "symbols": len(file_symbols),
                "lines": result.get("lines", 0)
            })

        coverage_pct = (covered_symbols / total_symbols * 100) if total_symbols > 0 else 100.0

        return {
            "ok": True,
            "path": path,
            "total_symbols": total_symbols,
            "covered_symbols": covered_symbols,
            "uncovered_count": len(uncovered),
            "coverage_percentage": round(coverage_pct, 2),
            "min_coverage_threshold": min_coverage,
            "meets_threshold": coverage_pct >= min_coverage,
            "uncovered": uncovered[:100],
            "file_stats": file_stats
        }

    def gap_finder(self, path: str = ".", severity: str = "high") -> dict[str, Any]:
        """Find critical coverage gaps."""
        report = self.coverage_report(path)
        uncovered = report.get("uncovered", [])
        
        severity_map = {"high": 0, "medium": 1, "low": 2}
        priorities = {"high": [], "medium": [], "low": []}
        
        for item in uncovered:
            # Class-level symbols are high priority
            if item["type"] == "class":
                priorities["high"].append(item)
            elif item["type"] == "function":
                priorities["medium"].append(item)
            else:
                priorities["low"].append(item)

        return {
            "ok": True,
            "path": path,
            "severity": severity,
            "gaps": priorities.get(severity, uncovered[:50]),
            "gap_count": len(priorities.get(severity, [])),
            "all_priorities": {k: len(v) for k, v in priorities.items()}
        }

    def pattern_discovery(self, path: str = ".") -> dict[str, Any]:
        """Discover testing patterns used in the repository."""
        test_files = self._find_test_files(path)
        patterns = {
            "unittest_style": 0,
            "pytest_style": 0,
            "mock_usage": 0,
            "fixture_usage": 0,
            "parametrized": 0,
            "async_tests": 0,
            "skip_decorated": 0,
            "xfail": 0
        }

        for tf in test_files[:100]:
            try:
                content = tf.read_text(encoding='utf-8')
                if "unittest" in content:
                    patterns["unittest_style"] += 1
                if "pytest" in content or "import pytest" in content:
                    patterns["pytest_style"] += 1
                if "mock" in content.lower():
                    patterns["mock_usage"] += 1
                if "@pytest.fixture" in content:
                    patterns["fixture_usage"] += 1
                if "@pytest.mark.parametrize" in content or "@pytest.mark.param" in content:
                    patterns["parametrized"] += 1
                if "async def" in content:
                    patterns["async_tests"] += 1
                if "@pytest.mark.skip" in content or "@unittest.skip" in content:
                    patterns["skip_decorated"] += 1
                if "@pytest.mark.xfail" in content or "@unittest.expectedFailure" in content:
                    patterns["xfail"] += 1
            except Exception:
                continue

        return {
            "ok": True,
            "path": path,
            "test_files_analyzed": len(test_files),
            "patterns": patterns,
            "dominant_pattern": max(patterns, key=patterns.get) if patterns else "none"
        }

    def scaffold_generator(self, module_path: str = ".", test_style: str = "pytest") -> dict[str, Any]:
        """Generate test scaffolds for uncovered modules."""
        py_files = self._find_python_files(module_path, include_tests=False)
        test_files = self._find_test_files(module_path)
        
        scaffolds = []
        for pf in py_files:
            result = self._extract_symbols(pf)
            if "error" in result:
                continue
            symbols = result.get("symbols", [])
            if not symbols:
                continue
            
            # Check if already tested
            already_tested = False
            for sym in symbols:
                if self._check_coverage(sym, test_files):
                    already_tested = True
                    break
            
            if already_tested:
                continue

            # Generate scaffold
            class_name = pf.stem.capitalize()
            lines = []
            
            if test_style == "pytest":
                lines.append(f"import pytest")
                lines.append(f"from {pf.stem} import {class_name}")
                lines.append(f"")
                lines.append(f"class Test{class_name}:")
                for sym in symbols:
                    if sym["type"] == "function":
                        lines.append(f"    def test_{sym['name']}(self):")
                        lines.append(f"        # TODO: Implement test for {sym['name']}")
                        lines.append(f"        pass")
                        lines.append(f"")
            else:
                lines.append(f"import unittest")
                lines.append(f"from {pf.stem} import {class_name}")
                lines.append(f"")
                lines.append(f"class Test{className}(unittest.TestCase):")
                for sym in symbols:
                    if sym["type"] == "function":
                        lines.append(f"    def test_{sym['name']}(self):")
                        lines.append(f"        # TODO: Implement test for {sym['name']}")
                        lines.append(f"        self.assertTrue(True)")
                        lines.append(f"")

            scaffolds.append({
                "module": str(pf.relative_to(self.repo_root)),
                "test_file": f"test_{pf.stem}.py",
                "style": test_style,
                "scaffold": "\n".join(lines),
                "symbols_to_test": [s["name"] for s in symbols]
            })

        return {
            "ok": True,
            "module_path": module_path,
            "test_style": test_style,
            "scaffolds": scaffolds[:50],
            "scaffold_count": len(scaffolds)
        }

    def test_summary(self) -> dict[str, Any]:
        """Generate a summary of the test suite."""
        py_files = self._find_python_files(include_tests=False)
        test_files = self._find_test_files()
        
        total_code_lines = 0
        total_test_lines = 0
        
        for pf in py_files:
            try:
                total_code_lines += len(pf.read_text(encoding='utf-8').split('\n'))
            except Exception:
                pass
        
        for tf in test_files:
            try:
                total_test_lines += len(tf.read_text(encoding='utf-8').split('\n'))
            except Exception:
                pass

        return {
            "ok": True,
            "repo_root": str(self.repo_root),
            "python_files": len(py_files),
            "test_files": len(test_files),
            "code_lines": total_code_lines,
            "test_lines": total_test_lines,
            "test_to_code_ratio": round(total_test_lines / total_code_lines * 100, 2) if total_code_lines > 0 else 0
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_analyzer: TestCoverageAnalyzer | None = None

def _get_analyzer(repo_root: str) -> TestCoverageAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = TestCoverageAnalyzer(repo_root)
    return _analyzer


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_test_coverage_report"] = ToolSpec(
        name="aicarmine_test_coverage_report",
        description="Generate coverage report for a module/directory",
        input_schema=object_schema({
            "path": {"type": "string"},
            "min_coverage": {"type": "number"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).coverage_report(
            path=args.get("path", "."),
            min_coverage=args.get("min_coverage", 0.0)
        ),
    )

    tools["aicarmine_test_gap_finder"] = ToolSpec(
        name="aicarmine_test_gap_finder",
        description="Find critical coverage gaps",
        input_schema=object_schema({
            "path": {"type": "string"},
            "severity": {"type": "string", "enum": ["high", "medium", "low"]}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).gap_finder(
            path=args.get("path", "."),
            severity=args.get("severity", "high")
        ),
    )

    tools["aicarmine_test_pattern_discovery"] = ToolSpec(
        name="aicarmine_test_pattern_discovery",
        description="Discover testing patterns in the repository",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).pattern_discovery(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_test_scaffold_generator"] = ToolSpec(
        name="aicarmine_test_scaffold_generator",
        description="Generate test scaffolds for uncovered modules",
        input_schema=object_schema({
            "module_path": {"type": "string"},
            "test_style": {"type": "string", "enum": ["pytest", "unittest"]}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).scaffold_generator(
            module_path=args.get("module_path", "."),
            test_style=args.get("test_style", "pytest")
        ),
    )

    tools["aicarmine_test_summary"] = ToolSpec(
        name="aicarmine_test_summary",
        description="Generate summary of test suite",
        input_schema=object_schema(),
        handler=lambda args, root: _get_analyzer(str(root)).test_summary(),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())