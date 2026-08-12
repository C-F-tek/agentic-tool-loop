#!/usr/bin/env python3
"""CLI entrypoint for hardware/delegation contract validation."""
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

from Tools.validation.runtime_hardware_delegation_checks import (
    resolve_repo_path,
    split_values,
    validate_contract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--hardware-manifest", required=True)
    parser.add_argument("--delegated-report", action="append", default=[])
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    hardware_manifest = resolve_repo_path(repo_root, args.hardware_manifest)
    delegated_reports = [resolve_repo_path(repo_root, item) for item in split_values(args.delegated_report)]
    report = validate_contract(repo_root, hardware_manifest, delegated_reports)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
