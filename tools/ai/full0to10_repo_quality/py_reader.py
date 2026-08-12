"""Python static reader for repo quality packet."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .constants import MAX_PREVIEW_CHARS
from .paths import repo_relative


def safe_parse(text: str) -> tuple[ast.AST | None, str | None]:
    try:
        return ast.parse(text), None
    except SyntaxError as exc:
        return None, str(exc)


def read_python(repo_root: Path, path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    tree, error = safe_parse(text)
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
    lowered = text.lower()
    return {
        "path": repo_relative(path, repo_root),
        "kind": "python",
        "parse_ok": error is None,
        "parse_error": error,
        "line_count": text.count("\n") + 1,
        "function_count": len(functions),
        "class_count": len(classes),
        "functions": functions[:40],
        "classes": classes[:20],
        "imports": sorted(set(imports))[:40],
        "mentions": {
            "argparse": "argparse" in lowered,
            "subprocess": "subprocess" in lowered,
            "sqlite": "sqlite" in lowered,
            "provider": "provider" in lowered,
            "gpu": "gpu" in lowered,
            "npu": "npu" in lowered,
        },
        "preview": text[:MAX_PREVIEW_CHARS],
    }
