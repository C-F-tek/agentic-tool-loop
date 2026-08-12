#!/usr/bin/env python3
"""Validate that JSON artifacts are parseable without rewriting them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import failed_result_errors, resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import failed_result_errors, resolve_output_path, write_json_report  # type: ignore


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".repo_patch_backups",
    "renders",
}


def is_excluded(path: Path, repo_root: Path, excludes: set[str]) -> bool:
    try:
        rel_parts = path.relative_to(repo_root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in excludes for part in rel_parts)


def iter_json_files(repo_root: Path, excludes: set[str], include_index_ai: bool) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*.json"):
        if not include_index_ai and "indexAI" in path.parts:
            continue
        if is_excluded(path, repo_root, excludes):
            continue
        files.append(path)
    return sorted(files)


def read_json_text(path: Path) -> str:
    """Read JSON text, accepting UTF-8 files with or without BOM."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def inspect_json(path: Path, repo_root: Path, max_size_mb: float) -> dict[str, Any]:
    rel = path.relative_to(repo_root).as_posix()
    size = path.stat().st_size
    max_size = int(max_size_mb * 1024 * 1024)
    if size > max_size:
        return {
            "path": rel,
            "ok": True,
            "skipped": True,
            "reason": f"larger than max_size_mb={max_size_mb}",
            "size_bytes": size,
        }

    try:
        data = json.loads(read_json_text(path))
        return {
            "path": rel,
            "ok": True,
            "skipped": False,
            "type": type(data).__name__,
            "size_bytes": size,
            "top_level_keys": sorted(data.keys()) if isinstance(data, dict) else None,
            "item_count": len(data) if isinstance(data, list) else None,
        }
    except json.JSONDecodeError as exc:
        return {
            "path": rel,
            "ok": False,
            "skipped": False,
            "size_bytes": size,
            "error": f"line {exc.lineno}, column {exc.colno}: {exc.msg}",
        }
    except OSError as exc:
        return {
            "path": rel,
            "ok": False,
            "skipped": False,
            "size_bytes": size,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--include-index-ai", action="store_true")
    parser.add_argument("--max-size-mb", type=float, default=25.0)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    excludes = set(DEFAULT_EXCLUDES)
    excludes.update(args.exclude)

    files = iter_json_files(repo_root, excludes, args.include_index_ai)
    results = [inspect_json(path, repo_root, args.max_size_mb) for path in files]
    failed = [item for item in results if not item["ok"]]
    skipped = [item for item in results if item.get("skipped")]
    errors = failed_result_errors(results)

    report = {
        "schema_version": 1,
        "kind": "json_artifacts",
        "repo_root": repo_root.as_posix(),
        "checked_count": len(results) - len(skipped),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "passed": not failed,
        "errors": errors,
        "warnings": [],
        "include_index_ai": args.include_index_ai,
        "max_size_mb": args.max_size_mb,
        "results": results,
    }

    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
