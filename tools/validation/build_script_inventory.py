#!/usr/bin/env python3
"""Build a repository script/tool inventory with callable discovery.

Report-only validator. It scans source scripts, extracts lightweight metadata and
writes JSON, CSV and optional Markdown outputs. It does not import project modules
and does not run project code.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


SCRIPT_SUFFIXES = {".py", ".ps1", ".sh", ".bat", ".cmd"}
IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "output",
    "renders",
}
DEFAULT_OUTPUT = "output/validation/script_inventory.json"
DEFAULT_CSV_OUTPUT = "output/validation/script_inventory.csv"

POWERSHELL_FUNCTION_RE = re.compile(
    r"^\s*function\s+([A-Za-z_][A-Za-z0-9_\-:]*)\s*(?:\{|$)",
    re.IGNORECASE,
)
SHELL_FUNCTION_RE = re.compile(
    r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{",
)


@dataclass
class ScriptInventoryItem:
    path: str
    language: str
    category: str
    lines: int
    size_bytes: int
    description: str
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    has_main_guard: bool = False
    has_argparse: bool = False
    has_click: bool = False
    has_provider_terms: bool = False
    has_blender_terms: bool = False
    has_write_terms: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "category": self.category,
            "lines": self.lines,
            "size_bytes": self.size_bytes,
            "description": self.description,
            "function_count": len(self.functions),
            "class_count": len(self.classes),
            "method_count": len(self.methods),
            "functions": self.functions,
            "classes": self.classes,
            "methods": self.methods,
            "has_main_guard": self.has_main_guard,
            "has_argparse": self.has_argparse,
            "has_click": self.has_click,
            "has_provider_terms": self.has_provider_terms,
            "has_blender_terms": self.has_blender_terms,
            "has_write_terms": self.has_write_terms,
            "warnings": self.warnings,
        }


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def is_under_ignored_dir(path: Path, repo_root: Path) -> bool:
    try:
        rel_parts = path.resolve().relative_to(repo_root.resolve()).parts
    except ValueError:
        return True
    return any(part in IGNORED_DIR_NAMES for part in rel_parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".ps1":
        return "powershell"
    if suffix == ".sh":
        return "shell"
    if suffix in {".bat", ".cmd"}:
        return "windows_batch"
    return "unknown"


def category_for(rel_path: str) -> str:
    if rel_path.startswith("Tools/validation/"):
        return "validator"
    if rel_path.startswith("Tools/workflow/"):
        return "workflow_runner"
    if rel_path.startswith("Tools/ai/"):
        return "ai_tool"
    if rel_path.startswith("Tools/npu/"):
        return "npu_or_provider_tool"
    if rel_path.startswith("Tools/git/"):
        return "git_helper"
    if rel_path.startswith("Scripting/"):
        return "blender_application_script"
    if rel_path.startswith("examples/"):
        return "example"
    if "/test" in rel_path.lower() or rel_path.lower().startswith("test"):
        return "test_or_fixture"
    return "script"


def first_comment_description(text: str) -> str:
    comments: list[str] = []
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if not stripped:
            if comments:
                break
            continue
        if stripped.startswith("#!"):
            continue
        if stripped.startswith("#"):
            comments.append(stripped.lstrip("#").strip())
            continue
        if comments:
            break
    return " ".join(comments).strip()


def concise(text: str | None, max_chars: int = 220) -> str:
    if not text:
        return "not specified"
    flat = " ".join(text.strip().split())
    if not flat:
        return "not specified"
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1].rstrip() + "..."


def public_name(name: str) -> bool:
    return not name.startswith("_") or name == "__main__"


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def parse_python(path: Path, rel_path: str, text: str, lines: int) -> ScriptInventoryItem:
    warnings: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    methods: list[str] = []
    description = first_comment_description(text)
    has_argparse = "argparse" in text
    has_click = "click." in text or "import click" in text
    has_main_guard = "if __name__" in text and "__main__" in text

    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        warnings.append(f"python_syntax_error:{exc.lineno}:{exc.msg}")
        return ScriptInventoryItem(
            path=rel_path,
            language="python",
            category=category_for(rel_path),
            lines=lines,
            size_bytes=path.stat().st_size,
            description=concise(description),
            has_main_guard=has_main_guard,
            has_argparse=has_argparse,
            has_click=has_click,
            has_provider_terms=contains_any(text, ("ollama", "openvino", "npu", "gpu", "provider")),
            has_blender_terms=contains_any(text, ("bpy", "blender")),
            has_write_terms=contains_any(text, ("write_text", "write_bytes", "export-csv", "set-content")),
            warnings=warnings,
        )

    module_doc = ast.get_docstring(tree)
    description = concise(module_doc or description)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and public_name(node.name):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef) and public_name(node.name):
            classes.append(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and public_name(child.name):
                    methods.append(f"{node.name}.{child.name}")

    return ScriptInventoryItem(
        path=rel_path,
        language="python",
        category=category_for(rel_path),
        lines=lines,
        size_bytes=path.stat().st_size,
        description=description,
        functions=sorted(functions),
        classes=sorted(classes),
        methods=sorted(methods),
        has_main_guard=has_main_guard,
        has_argparse=has_argparse,
        has_click=has_click,
        has_provider_terms=contains_any(text, ("ollama", "openvino", "npu", "gpu", "provider")),
        has_blender_terms=contains_any(text, ("bpy", "blender")),
        has_write_terms=contains_any(text, ("write_text", "write_bytes", "export-csv", "set-content")),
        warnings=warnings,
    )


def parse_powershell(path: Path, rel_path: str, text: str, lines: int) -> ScriptInventoryItem:
    functions = []
    for line in text.splitlines():
        match = POWERSHELL_FUNCTION_RE.match(line)
        if match:
            functions.append(match.group(1))
    return ScriptInventoryItem(
        path=rel_path,
        language="powershell",
        category=category_for(rel_path),
        lines=lines,
        size_bytes=path.stat().st_size,
        description=concise(first_comment_description(text)),
        functions=sorted(set(functions)),
        has_provider_terms=contains_any(text, ("ollama", "openvino", "npu", "gpu", "provider")),
        has_blender_terms=contains_any(text, ("bpy", "blender")),
        has_write_terms=contains_any(text, ("export-csv", "set-content", "out-file")),
    )


def parse_shell_like(path: Path, rel_path: str, text: str, lines: int) -> ScriptInventoryItem:
    functions = []
    for line in text.splitlines():
        match = SHELL_FUNCTION_RE.match(line)
        if match:
            functions.append(match.group(1))
    return ScriptInventoryItem(
        path=rel_path,
        language=language_for(path),
        category=category_for(rel_path),
        lines=lines,
        size_bytes=path.stat().st_size,
        description=concise(first_comment_description(text)),
        functions=sorted(set(functions)),
        has_provider_terms=contains_any(text, ("ollama", "openvino", "npu", "gpu", "provider")),
        has_blender_terms=contains_any(text, ("bpy", "blender")),
        has_write_terms=contains_any(text, ("write", "export")),
    )


def collect_scripts(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for suffix in SCRIPT_SUFFIXES:
        for path in repo_root.rglob(f"*{suffix}"):
            if path.is_file() and not is_under_ignored_dir(path, repo_root):
                files.append(path)
    return sorted(set(files), key=lambda item: repo_relative(item, repo_root).lower())


def inventory_item(path: Path, repo_root: Path) -> ScriptInventoryItem:
    rel_path = repo_relative(path, repo_root)
    text = read_text(path)
    lines = len(text.splitlines())
    suffix = path.suffix.lower()
    if suffix == ".py":
        return parse_python(path, rel_path, text, lines)
    if suffix == ".ps1":
        return parse_powershell(path, rel_path, text, lines)
    return parse_shell_like(path, rel_path, text, lines)


def count_by(items: Iterable[ScriptInventoryItem], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(getattr(item, attr))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_report(repo_root: Path) -> dict[str, Any]:
    items = [inventory_item(path, repo_root) for path in collect_scripts(repo_root)]
    warning_items = [item for item in items if item.warnings]
    return {
        "schema_version": 1,
        "kind": "script_inventory",
        "repo_root": str(repo_root),
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "script_count": len(items),
        "language_counts": count_by(items, "language"),
        "category_counts": count_by(items, "category"),
        "with_main_guard_count": sum(1 for item in items if item.has_main_guard),
        "with_provider_terms_count": sum(1 for item in items if item.has_provider_terms),
        "with_blender_terms_count": sum(1 for item in items if item.has_blender_terms),
        "with_write_terms_count": sum(1 for item in items if item.has_write_terms),
        "syntax_warning_count": sum(len(item.warnings) for item in warning_items),
        "items": [item.to_dict() for item in items],
        "errors": [],
        "warnings": [warning for item in warning_items for warning in item.warnings],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "path",
        "language",
        "category",
        "lines",
        "description",
        "function_count",
        "class_count",
        "method_count",
        "functions",
        "classes",
        "methods",
        "has_main_guard",
        "has_argparse",
        "has_provider_terms",
        "has_blender_terms",
        "has_write_terms",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in report["items"]:
            row = dict(item)
            row["functions"] = ";".join(row.get("functions") or [])
            row["classes"] = ";".join(row.get("classes") or [])
            row["methods"] = ";".join(row.get("methods") or [])
            row["warnings"] = ";".join(row.get("warnings") or [])
            writer.writerow({field: row.get(field, "") for field in fields})


def render_markdown(report: dict[str, Any], max_rows: int) -> str:
    lines: list[str] = []
    lines.append("# Script and Tool Inventory")
    lines.append("")
    lines.append(f"- Kind: `{report['kind']}`")
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Script count: `{report['script_count']}`")
    lines.append(f"- Syntax warning count: `{report['syntax_warning_count']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    lines.append("## Category counts")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    for key, value in report["category_counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.append("")
    lines.append("## Inventory sample")
    lines.append("")
    lines.append("| Path | Language | Category | Lines | Description | Functions/classes |")
    lines.append("|---|---|---|---:|---|---|")
    for item in report["items"][:max_rows]:
        callables = []
        if item["functions"]:
            callables.append("fn: " + ", ".join(item["functions"][:8]))
        if item["classes"]:
            callables.append("class: " + ", ".join(item["classes"][:6]))
        callables_text = "<br>".join(callables) if callables else "not specified"
        description = str(item["description"]).replace("|", "\\|")
        lines.append(
            f"| `{item['path']}` | `{item['language']}` | `{item['category']}` | "
            f"{item['lines']} | {description} | {callables_text} |"
        )
    if len(report["items"]) > max_rows:
        lines.append("")
        lines.append(f"_Rows truncated in Markdown view: {max_rows}/{len(report['items'])}. Use CSV/JSON for full inventory._")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a report-only inventory of repository scripts and tools.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="JSON output path.")
    parser.add_argument("--csv-output", default=DEFAULT_CSV_OUTPUT, help="CSV output path.")
    parser.add_argument("--markdown-output", default=None, help="Optional Markdown output path.")
    parser.add_argument("--markdown-max-rows", type=int, default=120, help="Maximum Markdown rows to render.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root)
    write_json(Path(args.output), report)
    write_csv(Path(args.csv_output), report)
    if args.markdown_output:
        Path(args.markdown_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown_output).write_text(
            render_markdown(report, max_rows=args.markdown_max_rows),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
