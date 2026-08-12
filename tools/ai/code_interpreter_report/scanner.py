"""AST scanner for static code interpreter reports."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from Tools.ai.code_interpreter_report.constants import BRANCH_NODES, RISK_CALLS, TODO_PATTERN
from Tools.ai.code_patch_plan_common import compact_text, repo_rel
from Tools.ai.github_evidence_bundle_io import line_count, read_text


def split_csv_values(values: list[str]) -> set[str]:
    """Expand repeated comma-separated CLI values into a set."""
    return {item.strip() for value in values for item in value.split(",") if item.strip()}


def excluded_by_dir(path: Path, repo_root: Path, excluded_dirs: set[str]) -> bool:
    """Return true when any relative path component is excluded."""
    try:
        parts = path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).parts
    except ValueError:
        parts = path.parts
    return any(part in excluded_dirs for part in parts)


def iter_python_files(repo_root: Path, roots: list[Path], excluded_dirs: set[str]) -> list[Path]:
    """Return sorted Python source files."""
    candidates: list[Path] = []
    search_roots = roots or [repo_root]
    for root in search_roots:
        if root.is_file() and root.suffix.lower() == ".py":
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(path for path in root.rglob("*.py") if path.is_file())
    filtered = [path for path in candidates if not excluded_by_dir(path, repo_root, excluded_dirs)]
    unique = {path.resolve(strict=False): path for path in filtered}
    return sorted(unique.values(), key=lambda path: repo_rel(repo_root, path).lower())


def resolve_roots(repo_root: Path, values: list[str]) -> list[Path]:
    """Resolve CLI input roots."""
    roots: list[Path] = []
    for value in values:
        raw = Path(value)
        roots.append(raw.resolve() if raw.is_absolute() else (repo_root / raw).resolve())
    return roots


def read_source(path: Path) -> tuple[str, str | None]:
    """Read source text."""
    return read_text(path)


def source_line_count(source: str) -> int:
    """Return a stable physical line count for source text."""
    return line_count(source)


def dotted_name(node: ast.AST) -> str:
    """Return dotted name for call/import expression when possible."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def line_span(node: ast.AST) -> int:
    """Return physical line span for a node."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if isinstance(start, int) and isinstance(end, int):
        return max(1, end - start + 1)
    return 0


def function_record(node: ast.AST) -> dict[str, Any]:
    """Return compact function/method metadata."""
    args = getattr(node, "args", None)
    arg_count = len(args.args) + len(args.kwonlyargs) if args else 0
    return {
        "name": getattr(node, "name", ""),
        "lineno": getattr(node, "lineno", None),
        "line_span": line_span(node),
        "arg_count": arg_count,
        "branch_count": sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODES)),
        "docstring_present": bool(ast.get_docstring(node)),
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def class_record(node: ast.ClassDef) -> dict[str, Any]:
    """Return compact class metadata."""
    methods = [child for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return {
        "name": node.name,
        "lineno": node.lineno,
        "line_span": line_span(node),
        "method_count": len(methods),
        "docstring_present": bool(ast.get_docstring(node)),
    }


def import_records(tree: ast.AST) -> list[dict[str, str]]:
    """Extract imports."""
    imports: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"type": "import", "name": alias.name, "asname": alias.asname or ""})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append({"type": "from", "module": module, "name": alias.name, "asname": alias.asname or ""})
    return imports


def risk_signals(tree: ast.AST) -> list[dict[str, Any]]:
    """Extract risky/static-interest call signals."""
    signals: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if name in RISK_CALLS:
            signals.append({"call": name, "category": RISK_CALLS[name], "lineno": getattr(node, "lineno", None)})
    return signals


def todo_signals(source: str) -> list[dict[str, Any]]:
    """Return TODO/FIXME-like comments."""
    out: list[dict[str, Any]] = []
    for index, line in enumerate(source.splitlines(), start=1):
        if TODO_PATTERN.search(line):
            out.append({"lineno": index, "text": compact_text(line.strip(), 240)})
    return out


def analyze_file(repo_root: Path, path: Path) -> dict[str, Any]:
    """Analyze one Python file without executing it."""
    rel = repo_rel(repo_root, path)
    source, read_error = read_source(path)
    base: dict[str, Any] = {
        "path": rel,
        "read_ok": read_error is None,
        "parse_ok": False,
        "errors": [read_error] if read_error else [],
        "line_count": source_line_count(source),
        "char_count": len(source),
    }
    if read_error:
        return base
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        base["errors"].append(f"SyntaxError:{exc.lineno}:{exc.offset}: {exc.msg}")
        return base

    functions = [function_record(node) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [class_record(node) for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    imports = import_records(tree)
    risks = risk_signals(tree)
    todos = todo_signals(source)
    branch_count = sum(1 for node in ast.walk(tree) if isinstance(node, BRANCH_NODES))
    large_functions = [item for item in functions if int(item.get("line_span") or 0) >= 80]
    complex_functions = [item for item in functions if int(item.get("branch_count") or 0) >= 12]

    base.update(
        {
            "parse_ok": True,
            "function_count": len(functions),
            "class_count": len(classes),
            "import_count": len(imports),
            "branch_count": branch_count,
            "todo_count": len(todos),
            "risk_signal_count": len(risks),
            "large_function_count": len(large_functions),
            "complex_function_count": len(complex_functions),
            "functions": sorted(functions, key=lambda item: int(item.get("line_span") or 0), reverse=True)[:30],
            "classes": sorted(classes, key=lambda item: int(item.get("line_span") or 0), reverse=True)[:30],
            "imports": imports[:80],
            "risk_signals": risks[:80],
            "todo_signals": todos[:60],
            "large_functions": large_functions[:20],
            "complex_functions": complex_functions[:20],
        }
    )
    return base
