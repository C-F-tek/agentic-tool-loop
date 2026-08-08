#!/usr/bin/env python3
"""MCP server for API surface analysis.

Extracts public API surfaces, maps relationships, tracks deprecations,
and validates API contracts across Python modules.
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

SERVER_NAME = "aicarmine-api-surface-mcp"
SERVER_VERSION = "1.0.0"


class APISurfaceAnalyzer:
    """Analyzes Python API surfaces."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    def _find_python_files(self, path: str | None = None) -> list[Path]:
        """Find all Python files."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        return sorted(target.rglob("*.py"), key=lambda p: p.relative_to(self.repo_root))

    def _parse_module(self, filepath: Path) -> dict[str, Any]:
        """Parse a Python module and extract its API surface."""
        try:
            source = filepath.read_text(encoding='utf-8')
            tree = ast.parse(source, str(filepath))
        except Exception as e:
            return {"error": str(e), "classes": [], "functions": [], "exports": []}

        classes = []
        functions = []
        exports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                public_methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef) and not m.name.startswith('_')]
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "public_methods": public_methods,
                    "bases": [getattr(b, 'id', str(b)) for b in node.bases]
                })
            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "params": [arg.arg for arg in node.args.args],
                        "decorators": [getattr(d, 'id', str(d)) for d in node.decorator_list]
                    })

        # Check for __all__ exports
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.append(elt.value)

        return {
            "classes": classes,
            "functions": functions,
            "exports": exports,
            "lines": source.count('\n') + 1
        }

    def surface_extract(self, path: str = ".") -> dict[str, Any]:
        """Extract the public API surface of a module/directory."""
        py_files = self._find_python_files(path)
        modules: list[dict[str, Any]] = []

        for pf in py_files:
            result = self._parse_module(pf)
            if "error" in result:
                continue
            modules.append({
                "file": str(pf.relative_to(self.repo_root)),
                "classes": result.get("classes", []),
                "functions": result.get("functions", []),
                "exports": result.get("exports", []),
                "lines": result.get("lines", 0)
            })

        total_classes = sum(len(m["classes"]) for m in modules)
        total_functions = sum(len(m["functions"]) for m in modules)

        return {
            "ok": True,
            "path": path,
            "modules_analyzed": len(modules),
            "total_public_classes": total_classes,
            "total_public_functions": total_functions,
            "api_surface": modules[:200]
        }

    def relationship_map(self, module: str = ".", depth: int = 2) -> dict[str, Any]:
        """Map relationships between modules."""
        py_files = self._find_python_files(module)
        imports_graph: dict[str, list[str]] = {}
        dependencies: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception:
                continue

            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            if imports:
                imports_graph[str(pf.relative_to(self.repo_root))] = imports
                dependencies.append({
                    "module": str(pf.relative_to(self.repo_root)),
                    "imports": imports[:20],
                    "import_count": len(imports)
                })

        return {
            "ok": True,
            "module": module,
            "depth": depth,
            "modules_with_imports": len(imports_graph),
            "total_dependencies": sum(len(v) for v in imports_graph.values()),
            "dependencies": dependencies[:100]
        }

    def deprecation_tracker(self, path: str = ".") -> dict[str, Any]:
        """Track deprecated APIs."""
        py_files = self._find_python_files(path)
        deprecated_items: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check for @deprecated decorator
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Name) and dec.id == 'deprecated':
                            deprecated_items.append({
                                "type": "function",
                                "name": node.name,
                                "file": str(pf.relative_to(self.repo_root)),
                                "line": node.lineno
                            })
                        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == 'deprecated':
                            deprecated_items.append({
                                "type": "function",
                                "name": node.name,
                                "file": str(pf.relative_to(self.repo_root)),
                                "line": node.lineno,
                                "message": getattr(dec.args[0], 'value', 'No message') if dec.args else "Deprecated"
                            })

                elif isinstance(node, ast.ClassDef):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Name) and dec.id == 'deprecated':
                            deprecated_items.append({
                                "type": "class",
                                "name": node.name,
                                "file": str(pf.relative_to(self.repo_root)),
                                "line": node.lineno
                            })

            # Check for deprecation warnings in docstrings
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    docstring = ast.get_docstring(node)
                    if docstring:
                        lower_doc = docstring.lower()
                        if 'deprecated' in lower_doc or 'deprecation' in lower_doc:
                            deprecated_items.append({
                                "type": f"class_{node.__class__.__name__.lower()}",
                                "name": getattr(node, 'name', 'unknown'),
                                "file": str(pf.relative_to(self.repo_root)),
                                "line": node.lineno,
                                "reason": "docstring mentions deprecation"
                            })

        return {
            "ok": True,
            "path": path,
            "deprecated_count": len(deprecated_items),
            "deprecated_items": deprecated_items[:100]
        }

    def contract_validator(self, module_path: str = ".", strict: bool = False) -> dict[str, Any]:
        """Validate API contracts (type hints, docstrings)."""
        py_files = self._find_python_files(module_path)
        issues: list[dict[str, Any]] = []
        compliant = 0

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                tree = ast.parse(source, str(pf))
            except Exception as e:
                issues.append({
                    "file": str(pf.relative_to(self.repo_root)),
                    "issue": f"Parse error: {str(e)}",
                    "severity": "error"
                })
                continue

            file_issues = []
            file_compliant = True

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    # Check for type hints
                    if not node.returns:
                        if strict:
                            file_issues.append({
                                "type": "function",
                                "name": node.name,
                                "issue": "Missing return type hint"
                            })
                            file_compliant = False

                    # Check for docstring
                    if not ast.get_docstring(node):
                        file_issues.append({
                            "type": "function",
                            "name": node.name,
                            "issue": "Missing docstring"
                        })
                        file_compliant = False

            if file_issues:
                issues.extend(file_issues)
            else:
                compliant += 1

        return {
            "ok": True,
            "module_path": module_path,
            "strict_mode": strict,
            "files_analyzed": len(py_files),
            "compliant_count": compliant,
            "issues_count": len(issues),
            "issues": issues[:200]
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_analyzer: APISurfaceAnalyzer | None = None

def _get_analyzer(repo_root: str) -> APISurfaceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = APISurfaceAnalyzer(repo_root)
    return _analyzer


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_surface_extract"] = ToolSpec(
        name="aicarmine_surface_extract",
        description="Extract public API surface of a module/directory",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).surface_extract(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_relationship_map"] = ToolSpec(
        name="aicarmine_relationship_map",
        description="Map relationships between modules",
        input_schema=object_schema({
            "module": {"type": "string"},
            "depth": {"type": "integer"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).relationship_map(
            module=args.get("module", "."),
            depth=args.get("depth", 2)
        ),
    )

    tools["aicarmine_deprecation_tracker"] = ToolSpec(
        name="aicarmine_deprecation_tracker",
        description="Track deprecated APIs",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).deprecation_tracker(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_contract_validator"] = ToolSpec(
        name="aicarmine_contract_validator",
        description="Validate API contracts (type hints, docstrings)",
        input_schema=object_schema({
            "module_path": {"type": "string"},
            "strict": {"type": "boolean"}
        }),
        handler=lambda args, root: _get_analyzer(str(root)).contract_validator(
            module_path=args.get("module_path", "."),
            strict=args.get("strict", False)
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())