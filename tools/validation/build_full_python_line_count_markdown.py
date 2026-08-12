#!/usr/bin/env python3
"""Render a complete Markdown inventory from a Python line-count CSV.

Report-only utility used by IA-Carmine startup/refactor workflows. It does not
scan source files itself; the authoritative source remains
Tools/validation/build_python_line_count_csv.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from Tools.validation.report_utils import resolve_output_path, write_full_python_line_count_markdown, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import resolve_output_path, write_full_python_line_count_markdown, write_json_report


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    stamp = args.stamp or now_stamp()
    csv_path = resolve_output_path(repo_root, args.csv)
    output = resolve_output_path(repo_root, args.output)
    result = write_full_python_line_count_markdown(stamp=stamp, csv_path=csv_path, output=output)
    report = {
        "schema_version": 1,
        "kind": "full_python_line_count_markdown",
        "repo_root": str(repo_root),
        "stamp": stamp,
        "passed": csv_path.exists() and output.exists(),
        "errors": [] if csv_path.exists() and output.exists() else [f"missing csv or output: {csv_path} -> {output}"],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "csv_path": result["csv_path"],
        "markdown_path": result["markdown_path"],
        "file_count": result["file_count"],
        "total_lines": result["total_lines"],
    }
    if args.report_output:
        write_json_report(report, resolve_output_path(repo_root, args.report_output))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
