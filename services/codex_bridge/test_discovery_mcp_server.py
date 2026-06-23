#!/usr/bin/env python3
"""MCP server for test discovery, scaffolding, and coverage gap analysis."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import ast
from pathlib import Path
from typing import Any
from collections import defaultdict

from repo_mcp_common import (
    ToolSpec,
    handle_request,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-test-discovery-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Test Discovery Engine
# ---------------------------------------------------------------------------

class TestDiscoveryManager:
    """Discovers test patterns, generates scaffolds, and finds coverage gaps."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    def discover_test_patterns(self, path: str = ".", min_tests: int = 3) -> dict[str, Any]:
        """Discover existing test patterns in the codebase."""
        tests_dir = self.repo_root / "tests"
        if not path and str(tests_dir.exists()):
            target = tests_dir
        else:
            target = self.repo_root / path

        if not target.exists():
            return {"ok": True, "patterns": [], "message": f"Path not found: {target}"}

        test_files = list(target.rglob("test_*.py"))
        patterns = self._analyze_test_patterns(test_files)
        return {
            "ok": True,
            "path": str(target),
            "test_file_count": len(test_files),
            "pattern_count": len(patterns),
            "patterns": patterns[:min_tests * 5],
        }

    def find_uncovered_functions(self, source_path: str = ".", min_coverage: float = 0.8) -> dict[str, Any]:
        """Find public functions/classes with no corresponding tests."""
        source_file = self.repo_root / source_path
        if not source_file.exists():
            return {"ok": True, "uncovered": [], "message": f"Path not found: {source_file}"}

        symbols = self._extract_public_symbols(str(source_file))
        test_name = f"test_{source_file.stem}"
        test_dir = self.repo_root / "tests"
        test_files = list(test_dir.rglob(f"{test_name}*.py")) if test_dir.exists() else []

        uncovered = []
        for sym in symbols:
            if not self._has_test_for_symbol(sym, test_files):
                uncovered.append({
                    "name": sym["name"],
                    "type": sym["type"],
                    "file": str(source_file.relative_to(self.repo_root)),
                    "line": sym["line"],
                })

        return {
            "ok": True,
            "source_file": str(source_file.relative_to(self.repo_root)),
            "total_symbols": len(symbols),
            "uncovered_count": len(uncovered),
            "uncovered": uncovered[:50],
        }

    def generate_test_scaffold(
        self,
        target_path: str,
        scaffold_type: str = "class",
        include_docstrings: bool = True,
        include_assertions: bool = True,
    ) -> dict[str, Any]:
        """Generate a test scaffold for a given source file."""
        source_file = self.repo_root / target_path
        if not source_file.exists():
            return {"ok": True, "error": f"Path not found: {source_file}"}

        symbols = self._extract_public_symbols(str(source_file))
        module_name = source_file.stem
        test_class_name = self._to_test_class_name(module_name)

        if scaffold_type == "class":
            template = self._generate_class_scaffold(
                test_class_name, symbols, include_docstrings, include_assertions
            )
        else:
            template = self._generate_function_scaffold(
                symbols, include_docstrings, include_assertions
            )

        return {
            "ok": True,
            "target_file": str(source_file.relative_to(self.repo_root)),
            "scaffold_type": scaffold_type,
            "symbol_count": len(symbols),
            "generated_code": template,
        }

    def map_tests_to_sources(self, path: str = ".") -> dict[str, Any]:
        """Map existing tests to their source files."""
        tests_dir = self.repo_root / "tests"
        if not path and tests_dir.exists():
            target = tests_dir
        else:
            target = self.repo_root / path

        if not target.exists():
            return {"ok": True, "mapping": {}, "message": f"Path not found: {target}"}

        test_files = list(target.rglob("test_*.py"))
        mapping = self._build_test_source_mapping(test_files)

        return {
            "ok": True,
            "path": str(target),
            "test_file_count": len(test_files),
            "source_coverage": len(mapping),
            "mapping": mapping,
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _analyze_test_patterns(self, test_files: list[Path]) -> list[dict[str, Any]]:
        patterns = []
        for tf in test_files[:20]:
            try:
                source = tf.read_text(encoding="utf-8")
                tree = ast.parse(source)
                classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
                functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                patterns.append({
                    "file": str(tf.relative_to(self.repo_root)),
                    "test_class_count": len(classes),
                    "test_function_count": len(functions),
                    "imports": self._extract_imports(source),
                })
            except Exception:
                continue
        return patterns

    def _extract_imports(self, source: str) -> list[str]:
        try:
            tree = ast.parse(source)
            imports = []
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = [a.name for a in node.names]
                    imports.append(f"from {module} import {', '.join(names)}")
            return imports[:10]
        except Exception:
            return []

    def _extract_public_symbols(self, file_path: str) -> list[dict[str, Any]]:
        source = Path(file_path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        symbols = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    symbols.append({
                        "name": node.name,
                        "type": "function",
                        "line": node.lineno,
                        "args": self._get_function_args(node),
                    })
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    symbols.append({
                        "name": node.name,
                        "type": "class",
                        "line": node.lineno,
                    })
        return symbols

    def _get_function_args(self, func_node: ast.FunctionDef) -> list[str]:
        args = []
        for arg in func_node.args.args:
            if arg.arg != "self":
                args.append(arg.arg)
        return args[:5]

    def _has_test_for_symbol(self, symbol: dict[str, Any], test_files: list[Path]) -> bool:
        name = symbol["name"]
        pattern = f"def test_{name}("
        alt_pattern = f"class Test{name}"
        for tf in test_files[:20]:
            try:
                content = tf.read_text(encoding="utf-8")
                if pattern in content or alt_pattern in content or f"test_{name}" in content:
                    return True
            except Exception:
                continue
        return False

    def _to_test_class_name(self, module_name: str) -> str:
        parts = module_name.split("_")
        return "".join(p.title() for p in parts if p) + "Test"

    def _generate_class_scaffold(
        self,
        class_name: str,
        symbols: list[dict[str, Any]],
        include_docstrings: bool,
        include_assertions: bool,
    ) -> str:
        lines = [
            '"""Auto-generated test scaffold."""',
            f"import pytest",
            "",
            "",
            f"class Test{class_name}:  # Replace with actual test class name",
            '    """Test suite for the target module."""',
            "",
            "    @classmethod",
            "    def setup_class(cls):",
            '        """Set up test fixtures."""',
            "        pass",
            "",
            "    @classmethod",
            "    def teardown_class(cls):",
            '        """Clean up after tests."""',
            "        pass",
            "",
        ]

        for sym in symbols[:10]:
            if sym["type"] == "function":
                args = ", ".join(sym.get("args", []))
                lines.extend([
                    f"    def test_{sym['name']}_{self._generate_stub_suffix(len(args))}:",
                    f'        """Test {sym["name"]}."""',
                    f"        # Replace with actual assertions",
                    f"        # result = TargetClass.{sym['name']}({args})",
                    f"        # assert result is not None",
                    "",
                ])
            elif sym["type"] == "class":
                lines.extend([
                    f"    def test_{sym['name']}_instantiation(self):",
                    f'        """Test {sym["name"]} can be instantiated."""',
                    f"        # obj = {sym['name']}()",
                    f"        # assert obj is not None",
                    "",
                ])

        lines.append("")
        if include_docstrings:
            lines.extend([
                'if __name__ == "__main__":',
                '    import pytest',
                '    pytest.main([__file__, "-v"])',
                "",
            ])

        return "\n".join(lines)

    def _generate_function_scaffold(
        self,
        symbols: list[dict[str, Any]],
        include_docstrings: bool,
        include_assertions: bool,
    ) -> str:
        lines = [
            '"""Auto-generated function test scaffold."""',
            "import pytest",
            "",
            "",
        ]

        for sym in symbols[:10]:
            args = ", ".join(sym.get("args", []))
            lines.extend([
                f"def test_{sym['name']}({args}):",
                f'    """Test {sym["name"]} function."""',
                f"    # Replace with actual test logic",
                f"    # from your_module import {sym['name']}",
                f"    # result = {sym['name']}({args})",
                f"    # assert result is not None",
                "",
                "",
            ])

        return "\n".join(lines)

    def _generate_stub_suffix(self, arg_count: int) -> str:
        suffixes = ["", "_arg1", "_arg2", "_args_kwargs", "_many_args"]
        return suffixes[min(arg_count, len(suffixes) - 1)]

    def _build_test_source_mapping(self, test_files: list[Path]) -> dict[str, list[str]]:
        mapping = defaultdict(list)
        for tf in test_files[:50]:
            try:
                content = tf.read_text(encoding="utf-8")
                # Extract import statements to find source module
                for line in content.split("\n"):
                    if line.startswith("from ") or line.startswith("import "):
                        parts = line.split()
                        if len(parts) >= 2:
                            module = parts[1].split(".")[0]
                            mapping[module].append(str(tf.relative_to(self.repo_root)))
                        break
            except Exception:
                continue
        return dict(mapping)


# Module-level singleton
_test_manager: TestDiscoveryManager | None = None
_lock = threading.Lock()


def _get_test_manager(repo_root: str) -> TestDiscoveryManager:
    global _test_manager
    if _test_manager is None:
        with _lock:
            if _test_manager is None:
                _test_manager = TestDiscoveryManager(repo_root)
    return _test_manager


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["test_discovery"] = {
            "enabled": True,
            "manager": "TestDiscoveryManager",
        }
        return payload

    tools["aicarmine_test_discovery_health"] = ToolSpec(
        name="aicarmine_test_discovery_health",
        description="Report test discovery MCP health.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_test_discover_patterns"] = ToolSpec(
        name="aicarmine_test_discover_patterns",
        description="Discover existing test patterns in the repository.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
            "min_tests": {"type": "integer", "default": 3, "minimum": 1, "maximum": 100},
        }),
        handler=lambda args, root: _get_test_manager(str(root)).discover_test_patterns(
            args.get("path", "."), args.get("min_tests", 3)
        ),
    )

    tools["aicarmine_test_find_uncovered"] = ToolSpec(
        name="aicarmine_test_find_uncovered",
        description="Find public symbols with no corresponding tests.",
        input_schema=object_schema({
            "source_path": {"type": "string", "default": "."},
            "min_coverage": {"type": "number", "default": 0.8, "minimum": 0.0, "maximum": 1.0},
        }),
        handler=lambda args, root: _get_test_manager(str(root)).find_uncovered_functions(
            args.get("source_path", "."), args.get("min_coverage", 0.8)
        ),
    )

    tools["aicarmine_test_generate_scaffold"] = ToolSpec(
        name="aicarmine_test_generate_scaffold",
        description="Generate a test scaffold for a source file.",
        input_schema=object_schema({
            "target_path": {"type": "string"},
            "scaffold_type": {"type": "string", "enum": ["class", "function"], "default": "class"},
            "include_docstrings": {"type": "boolean", "default": True},
            "include_assertions": {"type": "boolean", "default": True},
        }, required=["target_path"]),
        handler=lambda args, root: _get_test_manager(str(root)).generate_test_scaffold(
            args["target_path"],
            args.get("scaffold_type", "class"),
            args.get("include_docstrings", True),
            args.get("include_assertions", True),
        ),
    )

    tools["aicarmine_test_map_tests"] = ToolSpec(
        name="aicarmine_test_map_tests",
        description="Map existing tests to their source files.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
        }),
        handler=lambda args, root: _get_test_manager(str(root)).map_tests_to_sources(
            args.get("path", ".")
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())