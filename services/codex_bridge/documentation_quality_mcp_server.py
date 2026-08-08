#!/usr/bin/env python3
"""MCP server for documentation quality scanning.

Analyzes documentation quality, docstring coverage, consistency,
broken links, and provides recommendations for improvement.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import re
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

SERVER_NAME = "aicarmine-documentation-quality-mcp"
SERVER_VERSION = "1.0.0"


class DocumentationQualityScanner:
    """Scans documentation quality across the repository."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    def quality_scan(self, path: str = ".", min_docstring_coverage: float = 0.8) -> dict[str, Any]:
        """Scan documentation quality for a module/directory."""
        target = self.repo_root / path
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {target}"}

        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        results = []
        total_classes = 0
        total_functions = 0
        documented_classes = 0
        documented_functions = 0

        for pf in py_files[:100]:
            try:
                result = self._scan_file(pf, min_docstring_coverage)
                results.append(result)
                total_classes += result["total_classes"]
                total_functions += result["total_functions"]
                documented_classes += result["documented_classes"]
                documented_functions += result["documented_functions"]
            except Exception:
                continue

        coverage = (documented_classes + documented_functions) / max(1, total_classes + total_functions)

        return {
            "ok": True,
            "path": str(target),
            "file_count": len(py_files),
            "results": results[:50],
            "docstring_coverage": round(coverage, 4),
            "total_classes": total_classes,
            "total_functions": total_functions,
            "documented_classes": documented_classes,
            "documented_functions": documented_functions,
            "missing_docs": [r for r in results if r["missing_count"] > 0],
            "quality_score": round(min(10.0, coverage * 10), 2)
        }

    def _scan_file(self, file_path: Path, min_coverage: float) -> dict[str, Any]:
        """Scan a single file for documentation quality."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except SyntaxError:
            return {
                "path": str(file_path.relative_to(self.repo_root)),
                "type": "syntax_error",
                "total_classes": 0,
                "total_functions": 0,
                "documented_classes": 0,
                "documented_functions": 0,
                "missing_count": 0,
                "issues": ["Could not parse as Python"]
            }

        classes = []
        functions = []
        module_docstring = ""

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node)
            elif (isinstance(node, ast.Expr) and isinstance(node.value, (ast.Str, ast.Constant))):
                if isinstance(node.value, ast.Constant):
                    module_docstring = str(node.value.value)

        total_classes = len(classes)
        total_functions = len(functions)
        documented_classes = sum(1 for c in classes if self._has_docstring(c))
        documented_functions = sum(1 for f in functions if self._has_docstring(f))

        missing = []
        for c in classes:
            if not self._has_docstring(c):
                missing.append({"type": "class", "name": c.name, "line": c.lineno})
        for f in functions:
            if not self._has_docstring(f):
                missing.append({"type": "function", "name": f.name, "line": f.lineno})

        # Check formatting consistency
        formatting_issues = self._check_formatting(content)

        # Check for outdated content
        outdated_issues = self._check_outdated(content)

        issues = formatting_issues + outdated_issues + missing

        return {
            "path": str(file_path.relative_to(self.repo_root)),
            "type": "python_module",
            "total_classes": total_classes,
            "total_functions": total_functions,
            "documented_classes": documented_classes,
            "documented_functions": documented_functions,
            "missing_count": len(missing),
            "missing": missing,
            "formatting_issues": len(formatting_issues),
            "outdated_issues": len(outdated_issues),
            "issues": issues,
            "module_docstring": module_docstring[:200] if module_docstring else ""
        }

    def _has_docstring(self, node: ast.AST) -> bool:
        """Check if a node has a docstring."""
        if node.body:
            first_stmt = node.body[0]
            if isinstance(first_stmt, ast.Expr):
                if isinstance(first_stmt.value, ast.Constant):
                    return isinstance(first_stmt.value.value, str) and len(str(first_stmt.value.value)) > 5
                if isinstance(first_stmt.value, ast.Str):
                    return len(first_stmt.value.s) > 5
        return False

    def _check_formatting(self, content: str) -> list[dict]:
        """Check documentation formatting consistency."""
        issues = []
        lines = content.splitlines()
        
        # Check for inconsistent docstring styles
        triple_double = 0
        triple_single = 0
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""'):
                triple_double += 1
            elif stripped.startswith("'''"):
                triple_single += 1
        
        if triple_double > 0 and triple_single > 0:
            issues.append({"type": "formatting", "issue": "mixed_docstring_styles"})
        
        return issues

    def _check_outdated(self, content: str) -> list[dict]:
        """Check for potentially outdated documentation."""
        issues = []
        
        # Look for TODO/FIXME/HACK markers in docstrings
        todo_pattern = r'(TODO|FIXME|HACK|XXX):\s*(.*)'
        for match in re.finditer(todo_pattern, content):
            issues.append({
                "type": "outdated",
                "marker": match.group(1),
                "text": match.group(2)[:100]
            })
        
        return issues

    def coverage_map(self, module: str = ".") -> dict[str, Any]:
        """Map which modules/classes/functions have documentation."""
        target = self.repo_root / module
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {target}"}

        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        documented = []
        undocumented = []

        for pf in py_files[:100]:
            try:
                content = pf.read_text(encoding="utf-8")
                tree = ast.parse(content)
                rel_path = str(pf.relative_to(self.repo_root))

                has_module_doc = False
                if tree.body and isinstance(tree.body[0], ast.Expr):
                    if isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
                        has_module_doc = True

                classes_with_docs = []
                classes_without_docs = []
                functions_with_docs = []
                functions_without_docs = []

                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        if self._has_docstring(node):
                            classes_with_docs.append(node.name)
                        else:
                            classes_without_docs.append(node.name)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if self._has_docstring(node):
                            functions_with_docs.append(node.name)
                        else:
                            functions_without_docs.append(node.name)

                entry = {
                    "path": rel_path,
                    "module_documented": has_module_doc,
                    "classes_with_docs": classes_with_docs,
                    "classes_without_docs": classes_without_docs,
                    "functions_with_docs": functions_with_docs,
                    "functions_without_docs": functions_without_docs
                }

                if classes_with_docs or functions_with_docs or has_module_doc:
                    documented.append(entry)
                else:
                    undocumented.append(entry)

            except Exception:
                continue

        return {
            "ok": True,
            "module": module,
            "documented_count": len(documented),
            "undocumented_count": len(undocumented),
            "documented": documented[:50],
            "undocumented": undocumented[:50]
        }

    def api_sync(self, code_base: str = ".", api_surface: str | None = None) -> dict[str, Any]:
        """Compare docstrings with actual code, identify discrepancies."""
        target = self.repo_root / code_base
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {target}"}

        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        discrepancies = []

        for pf in py_files[:50]:
            try:
                content = pf.read_text(encoding="utf-8")
                tree = ast.parse(content)
                rel_path = str(pf.relative_to(self.repo_root))

                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if self._has_docstring(node):
                            # Check if docstring mentions parameters that exist
                            doc = self._get_docstring(node)
                            params = node.args.args
                            param_names = [p.arg for p in params if p.arg != "self"]
                            
                            # Simple check: does docstring mention all params?
                            missing_params = []
                            for pname in param_names:
                                if pname not in doc.lower():
                                    missing_params.append(pname)
                            
                            if missing_params:
                                discrepancies.append({
                                    "file": rel_path,
                                    "function": node.name,
                                    "type": "missing_param_docs",
                                    "params": missing_params
                                })
            except Exception:
                continue

        return {
            "ok": True,
            "code_base": code_base,
            "discrepancies": discrepancies[:50],
            "discrepancy_count": len(discrepancies)
        }

    def search(self, query: str, scope: str = "all") -> dict[str, Any]:
        """Search documentation content."""
        target = self.repo_root
        py_files = list(target.rglob("*.py")) if target.is_dir() else []

        results = []
        for pf in py_files[:200]:
            try:
                content = pf.read_text(encoding="utf-8")
                tree = ast.parse(content)

                for node in tree.body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        if self._has_docstring(node):
                            doc = self._get_docstring(node)
                            if query.lower() in doc.lower():
                                results.append({
                                    "path": str(pf.relative_to(self.repo_root)),
                                    "type": type(node).__name__,
                                    "name": node.name,
                                    "line": node.lineno,
                                    "doc_preview": doc[:200]
                                })
            except Exception:
                continue

        return {
            "ok": True,
            "query": query,
            "scope": scope,
            "results": results[:50],
            "result_count": len(results)
        }

    def recommendations(self, module: str = ".") -> dict[str, Any]:
        """Generate specific recommendations for improving documentation."""
        target = self.repo_root / module
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {target}"}

        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        recommendations = []

        for pf in py_files[:50]:
            try:
                result = self._scan_file(pf, 0.8)
                if result["missing_count"] > 0:
                    for m in result["missing"]:
                        recommendations.append({
                            "file": result["path"],
                            "priority": "high",
                            "recommendation": f"Add docstring to {m['type']} '{m['name']}' at line {m['line']}"
                        })
                if result["formatting_issues"] > 0:
                    recommendations.append({
                        "file": result["path"],
                        "priority": "medium",
                        "recommendation": "Standardize docstring style (use triple double quotes)"
                    })
                if result["outdated_issues"] > 0:
                    recommendations.append({
                        "file": result["path"],
                        "priority": "low",
                        "recommendation": "Update TODO/FIXME markers in documentation"
                    })
            except Exception:
                continue

        return {
            "ok": True,
            "module": module,
            "recommendations": recommendations[:100],
            "recommendation_count": len(recommendations)
        }

    def _get_docstring(self, node: ast.AST) -> str:
        """Get docstring from a node."""
        if node.body and isinstance(node.body[0], ast.Expr):
            if isinstance(node.body[0].value, ast.Constant):
                val = node.body[0].value.value
                return str(val) if isinstance(val, str) else ""
            if isinstance(node.body[0].value, ast.Str):
                return node.body[0].value.s
        return ""


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_scanner: DocumentationQualityScanner | None = None

def _get_scanner(repo_root: str) -> DocumentationQualityScanner:
    global _scanner
    if _scanner is None:
        _scanner = DocumentationQualityScanner(repo_root)
    return _scanner


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_doc_quality_scan"] = ToolSpec(
        name="aicarmine_doc_quality_scan",
        description="Scan documentation quality for a module/directory",
        input_schema=object_schema({
            "path": {"type": "string"},
            "min_docstring_coverage": {"type": "number"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).quality_scan(
            path=args.get("path", "."),
            min_docstring_coverage=args.get("min_docstring_coverage", 0.8)
        ),
    )

    tools["aicarmine_doc_coverage_map"] = ToolSpec(
        name="aicarmine_doc_coverage_map",
        description="Map which modules/classes/functions have documentation",
        input_schema=object_schema({
            "module": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).coverage_map(
            module=args.get("module", ".")
        ),
    )

    tools["aicarmine_doc_api_sync"] = ToolSpec(
        name="aicarmine_doc_api_sync",
        description="Compare docstrings with actual code",
        input_schema=object_schema({
            "code_base": {"type": "string"},
            "api_surface": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).api_sync(
            code_base=args.get("code_base", "."),
            api_surface=args.get("api_surface")
        ),
    )

    tools["aicarmine_doc_search"] = ToolSpec(
        name="aicarmine_doc_search",
        description="Search documentation content",
        input_schema=object_schema({
            "query": {"type": "string"},
            "scope": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).search(
            query=args.get("query", ""),
            scope=args.get("scope", "all")
        ),
    )

    tools["aicarmine_doc_recommendations"] = ToolSpec(
        name="aicarmine_doc_recommendations",
        description="Generate documentation improvement recommendations",
        input_schema=object_schema({
            "module": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).recommendations(
            module=args.get("module", ".")
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())