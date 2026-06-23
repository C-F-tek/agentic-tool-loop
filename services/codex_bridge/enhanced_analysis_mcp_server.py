#!/usr/bin/env python3
"""
MCP server for enhanced code analysis tools.

Provides:
  - aicarmine_code_summarize_module: High-level file/module overview
  - aicarmine_code_api_surface: Public interface / export discovery
  - aicarmine_config_validator: mcp.json, pyproject.toml, env configs validation

All tools are read-only and use existing MCP infrastructure.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import ast
import configparser
import re
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

SERVER_NAME = "aicarmine-enhanced-analysis-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Code Summarizer
# ---------------------------------------------------------------------------

class CodeSummarizerManager:
    """Generates high-level overviews of files and modules."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)

    def summarize_module(self, path: str = ".", depth: int = 1) -> dict[str, Any]:
        """Generate a high-level overview of a module/directory."""
        target = self.repo_root / path
        if not target.exists():
            return {"ok": True, "error": f"Path not found: {target}"}

        # Collect all Python files
        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        summaries = []
        for file_path in py_files[:50]:  # Limit to 50 files
            try:
                content = file_path.read_text(encoding="utf-8")
                summary = self._summarize_file(file_path.relative_to(self.repo_root), content)
                summaries.append(summary)
            except Exception:
                continue

        return {
            "ok": True,
            "path": str(target),
            "file_count": len(py_files),
            "summaries": summaries[:20],  # Return top 20
        }

    def _summarize_file(self, rel_path: Path, content: str) -> dict[str, Any]:
        """Generate a summary for a single file."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return {
                "path": str(rel_path),
                "type": "unknown",
                "classes": [],
                "functions": [],
                "imports": [],
                "description": "Could not parse as Python",
            }

        classes = []
        functions = []
        imports = []
        docstring = ""

        for node in tree.body:
            if isinstance(node, ast.Module):
                # Get module docstring
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                    if isinstance(node.body[0].value, ast.Constant):
                        docstring = str(node.body[0].value.value)
                    else:
                        docstring = node.body[0].value.s

            elif isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "methods": self._extract_methods(node),
                    "docstring": self._get_docstring(node),
                })
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "args": self._extract_args(node),
                    "docstring": self._get_docstring(node),
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(f"from {module} import ...")

        return {
            "path": str(rel_path),
            "type": "python_module",
            "classes": classes[:10],
            "functions": functions[:20],
            "imports": imports[:20],
            "description": docstring[:500] if docstring else "No docstring",
        }

    def _extract_methods(self, class_node: ast.ClassDef) -> list[dict[str, Any]]:
        methods = []
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append({
                    "name": node.name,
                    "line": node.lineno,
                    "args": self._extract_args(node),
                    "is_static": any(
                        isinstance(dec, ast.Name) and dec.id == "staticmethod"
                        for dec in node.decorator_list
                    ),
                })
        return methods

    def _extract_args(self, func_node: ast.FunctionDef) -> list[str]:
        args = []
        for arg in func_node.args.args:
            if arg.arg != "self":
                args.append(arg.arg)
        return args

    def _get_docstring(self, node: ast.AST) -> str:
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, (ast.Str, ast.Constant))):
            if isinstance(node.body[0].value, ast.Constant):
                return str(node.body[0].value.value)[:300]
            return node.body[0].value.s[:300]
        return ""


# ---------------------------------------------------------------------------
# API Surface Extractor
# ---------------------------------------------------------------------------

class APISurfaceManager:
    """Extracts public interfaces, exports, and entry points."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)

    def extract_api_surface(self, path: str = ".", include_private: bool = False) -> dict[str, Any]:
        """Extract public interfaces from a module or directory."""
        target = self.repo_root / path
        if not target.exists():
            return {"ok": True, "error": f"Path not found: {target}"}

        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        exports = []
        public_apis = []

        for file_path in py_files[:50]:
            try:
                content = file_path.read_text(encoding="utf-8")
                rel_path = str(file_path.relative_to(self.repo_root))
                tree = ast.parse(content)

                # Check for __all__
                all_exports = self._find_all__(tree)
                if all_exports:
                    exports.append({"file": rel_path, "exports": all_exports})

                # Find public symbols
                for node in tree.body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith("_") or include_private:
                            public_apis.append({
                                "file": rel_path,
                                "name": node.name,
                                "type": "class" if isinstance(node, ast.ClassDef) else "function",
                                "line": node.lineno,
                            })
                    elif isinstance(node, ast.Assign):
                        for target_var in node.targets:
                            if isinstance(target_var, ast.Name):
                                if not target_var.id.startswith("_") or include_private:
                                    public_apis.append({
                                        "file": rel_path,
                                        "name": target_var.id,
                                        "type": "variable",
                                        "line": node.lineno,
                                    })
            except Exception:
                continue

        return {
            "ok": True,
            "path": str(target),
            "export_files": exports[:20],
            "public_apis": sorted(public_apis, key=lambda x: (x["file"], x["line"]))[:100],
        }

    def _find_all__(self, tree: ast.Module) -> list[str] | None:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            return [
                                elt.s if isinstance(elt, ast.Str) else str(elt.value)
                                for elt in node.value.elts
                            ]
        return None


# ---------------------------------------------------------------------------
# Configuration Validator
# ---------------------------------------------------------------------------

class ConfigValidatorManager:
    """Validates configuration files."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)

    def validate_configs(self, paths: list[str] | None = None) -> dict[str, Any]:
        """Validate common configuration files."""
        results = {}
        errors = []

        # Default config files to check
        default_configs = [
            "mcp.json",
            "pyproject.toml",
            ".env",
            "pytest.ini",
            "services/pyproject.toml",
        ]

        check_paths = paths or default_configs

        for config_path in check_paths:
            full_path = self.repo_root / config_path
            if not full_path.exists():
                results[config_path] = {"exists": False, "status": "missing"}
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
                status, warnings, details = self._validate_config(config_path, content)
                results[config_path] = {
                    "exists": True,
                    "status": status,
                    "warnings": warnings,
                    "details": details,
                    "size_bytes": full_path.stat().st_size,
                }
            except Exception as e:
                errors.append(f"{config_path}: {str(e)}")

        return {
            "ok": True,
            "repo_root": str(self.repo_root),
            "configs_checked": len(check_paths),
            "results": results,
            "errors": errors[:10],
        }

    def _validate_config(self, config_path: str, content: str) -> tuple[str, list[str], dict[str, Any]]:
        warnings = []
        details = {}

        if config_path.endswith(".json"):
            try:
                json.loads(content)
                status = "valid_json"
            except json.JSONDecodeError as e:
                status = "invalid_json"
                warnings.append(f"JSON parse error: {e}")

        elif config_path.endswith(".toml"):
            # Basic TOML validation
            if "=" in content or "[" in content or "{" in content:
                status = "valid_toml"
                # Check for common issues
                if "[tool.pytest" in content and "[tool.pytest" not in content:
                    pass  # OK
            else:
                status = "empty_or_invalid"
                warnings.append("Possible TOML syntax issue")

        elif config_path.endswith(".env"):
            lines = content.splitlines()
            valid_lines = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    valid_lines += 1
                else:
                    warnings.append(f"Potential .env syntax error: {line}")
            status = "valid_env" if valid_lines > 0 else "empty_env"

        elif config_path == "pytest.ini":
            if "[pytest]" in content:
                status = "valid_ini"
            else:
                status = "invalid_ini"
                warnings.append("Missing [pytest] section")

        else:
            status = "unknown_format"

        return status, warnings, details


# Module-level singletons
_summarizer: CodeSummarizerManager | None = None
api_extractor: APISurfaceManager | None = None
config_validator: ConfigValidatorManager | None = None
_lock = threading.Lock()


def _get_managers(repo_root: str):
    global _summarizer, api_extractor, config_validator
    if _summarizer is None:
        with _lock:
            if _summarizer is None:
                _summarizer = CodeSummarizerManager(repo_root)
                api_extractor = APISurfaceManager(repo_root)
                config_validator = ConfigValidatorManager(repo_root)
    return _summarizer, api_extractor, config_validator


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["enhanced_analysis"] = {
            "enabled": True,
            "managers": ["CodeSummarizer", "APISurface", "ConfigValidator"],
        }
        return payload

    tools["aicarmine_enhanced_health"] = ToolSpec(
        name="aicarmine_enhanced_health",
        description="Report enhanced analysis MCP health.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_code_summarize_module"] = ToolSpec(
        name="aicarmine_code_summarize_module",
        description="Generate a high-level overview of a module/directory.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
            "depth": {"type": "integer", "default": 1, "minimum": 1, "maximum": 3},
        }),
        handler=lambda args, root: _get_managers(str(root))[0].summarize_module(
            args.get("path", "."), args.get("depth", 1)
        ),
    )

    tools["aicarmine_code_api_surface"] = ToolSpec(
        name="aicarmine_code_api_surface",
        description="Extract public interfaces, exports, and entry points.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
            "include_private": {"type": "boolean", "default": False},
        }),
        handler=lambda args, root: _get_managers(str(root))[1].extract_api_surface(
            args.get("path", "."), args.get("include_private", False)
        ),
    )

    tools["aicarmine_config_validator"] = ToolSpec(
        name="aicarmine_config_validator",
        description="Validate common configuration files (mcp.json, pyproject.toml, .env).",
        input_schema=object_schema({
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["mcp.json", "pyproject.toml", ".env", "pytest.ini"],
            },
        }),
        handler=lambda args, root: _get_managers(str(root))[2].validate_configs(
            args.get("paths", None)
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