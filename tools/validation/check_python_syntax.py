#!/usr/bin/env python3
"""Validate Python syntax without importing project modules."""
from __future__ import annotations

import argparse
import py_compile
from pathlib import Path
from typing import Any

try:
    from report_utils import failed_result_errors, resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import failed_result_errors, resolve_output_path, write_json_report  # type: ignore


DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".repo_patch_backups",
    "indexAI",
    "output",
    "renders",
}


def is_excluded(path: Path, repo_root: Path, excludes: set[str]) -> bool:
    try:
        rel_parts = path.relative_to(repo_root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in excludes for part in rel_parts)


def iter_python_files(repo_root: Path, excludes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if is_excluded(path, repo_root, excludes):
            continue
        files.append(path)
    return sorted(files)


def check_file(path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        py_compile.compile(str(path), doraise=True)
        ok = True
        error = None
    except py_compile.PyCompileError as exc:
        ok = False
        error = str(exc)
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "ok": ok,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional directory or path component to exclude. Can be repeated.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    excludes = set(DEFAULT_EXCLUDES)
    excludes.update(args.exclude)

    files = iter_python_files(repo_root, excludes)
    results = [check_file(path, repo_root) for path in files]
    failed = [item for item in results if not item["ok"]]
    errors = failed_result_errors(results)

    report = {
        "schema_version": 1,
        "kind": "python_syntax",
        "repo_root": repo_root.as_posix(),
        "checked_count": len(results),
        "failed_count": len(failed),
        "passed": not failed,
        "errors": errors,
        "warnings": [],
        "excluded": sorted(excludes),
        "results": results,
    }

    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
