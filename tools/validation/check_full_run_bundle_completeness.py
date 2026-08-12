#!/usr/bin/env python3
"""CLI entrypoint for Full0To10 evidence ZIP completeness validation."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from pathlib import Path

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

from Tools.validation.full_run_bundle_completeness import (
    resolve_repo_path,
    split_values,
    validate_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--completeness-report")
    parser.add_argument("--required-recursive-root", action="append", default=[])
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    zip_path = resolve_repo_path(repo_root, args.bundle)
    report_path = resolve_repo_path(repo_root, args.completeness_report) if args.completeness_report else None
    report = validate_bundle(repo_root, zip_path, report_path, split_values(args.required_recursive_root))
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
