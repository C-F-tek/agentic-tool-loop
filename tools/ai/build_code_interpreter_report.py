#!/usr/bin/env python3
"""Build a static code interpreter report for Python source files.

This entrypoint keeps the CLI stable while the scanner, builder and renderer
live in Tools.ai.code_interpreter_report.

It does not execute providers, run Blender, apply patches or write source files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_interpreter_report.builder import build_report  # noqa: E402
from Tools.ai.code_interpreter_report.constants import (  # noqa: E402
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_MARKDOWN,
    DEFAULT_OUTPUT,
)
from Tools.ai.code_interpreter_report.render import render_markdown  # noqa: E402
from Tools.ai.code_interpreter_report.scanner import resolve_roots, split_csv_values  # noqa: E402
from Tools.ai.code_patch_plan_common import write_json_and_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--input", action="append", default=[], help="Optional file/dir roots; defaults to repo root.")
    parser.add_argument("--exclude-dir", action="append", default=[], help="Additional directory names to exclude.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_dirs.update(split_csv_values(args.exclude_dir))
    report = build_report(repo_root, resolve_roots(repo_root, args.input), excluded_dirs)
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
