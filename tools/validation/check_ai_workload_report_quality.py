#!/usr/bin/env python3
"""Validate textual quality of AI workload reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
VALIDATION_DIR = CURRENT.parent
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

from ai_workload_quality.constants import DEFAULT_REPORT_DIR  # noqa: E402
from ai_workload_quality.paths import split_path_values  # noqa: E402
from ai_workload_quality.reporter import build_quality_report, from_report_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--report", action="append", default=[], help="Strict report spec as lane=path. Repeatable or comma-separated.")
    parser.add_argument("--include-missing-known-reports", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args()


def explicit_specs(items: list[str]) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for item in split_path_values(items):
        if "=" not in item:
            raise SystemExit(f"Invalid --report value, expected lane=path: {item}")
        lane, raw_path = item.split("=", 1)
        specs.append((lane.strip(), raw_path.strip()))
    return specs


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = repo_root / report_dir

    specs = explicit_specs(list(args.report or []))
    if specs:
        report = build_quality_report(repo_root, specs, "explicit_reports", report_dir, [])
    else:
        report = from_report_dir(repo_root, report_dir, bool(args.include_missing_known_reports))

    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
