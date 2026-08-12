#!/usr/bin/env python3
"""Build deterministic Python line-count CSV evidence.

This utility replaces ad-hoc shell snippets for repository Python line-count
collection. It is report-only: it reads source files and writes CSV/JSON/MD
summary artifacts to explicit output paths.

It does not execute providers, run Blender, apply patches or modify source
files.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    now_iso,
    report_only_guardrails,
    resolve_output_path,
    repo_rel,
    write_json_and_markdown,
)
from Tools.validation.report_utils import count_file_lines, split_csv_values  # noqa: E402


REPORT_KIND = "python_line_count_csv"
DEFAULT_CSV = "docs/LOCAL_VALIDATION_EVIDENCE/python_line_count_latest.csv"
DEFAULT_REPORT = "output/validation/python_line_count_latest.json"
DEFAULT_MARKDOWN = "output/validation/python_line_count_latest.md"
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "renders",
    "venv",
}
DEFAULT_EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def timestamp_from_iso(value: str) -> str:
    """Convert `YYYY-MM-DDTHH:MM:SS` to `YYYYMMDD-HHMMSS`."""
    return value.replace("-", "").replace(":", "").replace("T", "-")


def excluded_by_dir(path: Path, repo_root: Path, excluded_dirs: set[str]) -> bool:
    """Return true when any path component belongs to an excluded directory."""
    try:
        parts = path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).parts
    except ValueError:
        parts = path.parts
    return any(part in excluded_dirs for part in parts)


def should_include_python(path: Path, repo_root: Path, excluded_dirs: set[str], excluded_suffixes: set[str]) -> bool:
    """Return true when a path should be counted as source Python."""
    return path.suffix.lower() == ".py" and path.suffix.lower() not in excluded_suffixes and not excluded_by_dir(path, repo_root, excluded_dirs)


def iter_included_python_files(repo_root: Path, excluded_dirs: set[str], excluded_suffixes: set[str]) -> list[Path]:
    """Return included Python files in stable repository-relative order."""
    paths = [path for path in repo_root.rglob("*.py") if should_include_python(path, repo_root, excluded_dirs, excluded_suffixes)]
    return sorted(paths, key=lambda value: repo_rel(repo_root, value).lower())


def collect_python_counts(repo_root: Path, excluded_dirs: set[str], excluded_suffixes: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect line counts for included Python files."""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in iter_included_python_files(repo_root, excluded_dirs, excluded_suffixes):
        row, error = build_row(repo_root, path)
        if error:
            errors.append(error)
        else:
            rows.append(row)
    rows.sort(key=lambda row: (-int(row["Lines"]), str(row["File"]).lower()))
    return rows, errors


def build_row(repo_root: Path, path: Path) -> tuple[dict[str, Any], str | None]:
    """Build one CSV row or return an error string."""
    lines, error = count_file_lines(path)
    rel = repo_rel(repo_root, path)
    if error:
        return {}, f"{rel}: {error}"
    return {"File": rel, "Lines": lines}, None


def write_csv(rows: list[dict[str, Any]], output: Path) -> None:
    """Write line-count rows to CSV."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["File", "Lines"])
        writer.writeheader()
        writer.writerows(rows)


def build_report(repo_root: Path, rows: list[dict[str, Any]], errors: list[str], csv_path: Path, excluded_dirs: set[str]) -> dict[str, Any]:
    """Build JSON validation/evidence summary for the CSV output."""
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "csv_written": repo_rel(repo_root, csv_path),
        "file_count": len(rows),
        "total_lines": sum(int(row["Lines"]) for row in rows),
        "top_files": rows[:20],
        "excluded_dirs": sorted(excluded_dirs),
        "guardrails": report_only_guardrails(
            source_files_modified=False,
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown summary for human review."""
    lines = ["# Python Line Count CSV", ""]
    lines.extend(render_summary(report))
    lines.append("## Largest Python files")
    lines.append("")
    lines.extend(render_top_files(report.get("top_files", [])))
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This artifact is line-count evidence only. It is not a patch plan and it must not be committed from `output/**`.")
    return "\n".join(lines) + "\n"


def render_summary(report: dict[str, Any]) -> list[str]:
    """Render top-level report metadata."""
    return [
        f"- Passed: `{report['passed']}`",
        f"- CSV: `{report['csv_written']}`",
        f"- File count: `{report['file_count']}`",
        f"- Total lines: `{report['total_lines']}`",
        f"- Provider execution performed: `{report['provider_execution_performed']}`",
        f"- Patch application performed: `{report['patch_application_performed']}`",
        f"- Source writes performed: `{report['source_writes_performed']}`",
        "",
    ]


def render_top_files(rows: Any) -> list[str]:
    """Render top line-count rows."""
    if not rows:
        return ["- none"]
    return [f"- `{row['File']}` — `{row['Lines']}` lines" for row in rows]


def default_csv_path(repo_root: Path, timestamped: bool) -> Path:
    """Return default CSV path, optionally timestamped."""
    if not timestamped:
        return resolve_output_path(repo_root, DEFAULT_CSV)
    return repo_root / "docs" / "LOCAL_VALIDATION_EVIDENCE" / f"python_line_count_{timestamp_from_iso(now_iso())}.csv"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--csv-output", help="CSV output path. Defaults to docs/LOCAL_VALIDATION_EVIDENCE/python_line_count_latest.csv")
    parser.add_argument("--report-output", default=DEFAULT_REPORT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--timestamped", action="store_true", help="Write a timestamped CSV under docs/LOCAL_VALIDATION_EVIDENCE/.")
    parser.add_argument("--exclude-dir", action="append", default=[], help="Additional directory name to exclude; comma-separated values are accepted.")
    parser.add_argument("--include-default-excludes", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS) if args.include_default_excludes else set()
    excluded_dirs.update(split_csv_values(args.exclude_dir))
    csv_path = resolve_output_path(repo_root, args.csv_output) if args.csv_output else default_csv_path(repo_root, args.timestamped)

    rows, errors = collect_python_counts(repo_root, excluded_dirs, set(DEFAULT_EXCLUDED_SUFFIXES))
    write_csv(rows, csv_path)
    report = build_report(repo_root, rows, errors, csv_path, excluded_dirs)
    json_text = write_json_and_markdown(repo_root, report, args.report_output, args.markdown_output, render_markdown(report))
    print(json.dumps(json.loads(json_text), indent=2, ensure_ascii=False), end="\n")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
