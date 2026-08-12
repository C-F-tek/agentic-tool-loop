#!/usr/bin/env python3
"""Run NPU pipeline helper unit tests and emit a validation report."""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

from report_utils import resolve_output_path, write_json_report


def run_tests(repo_root: Path) -> dict[str, object]:
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    import test_npu_pipeline_helpers  # noqa: PLC0415

    suite = unittest.defaultTestLoader.loadTestsFromModule(test_npu_pipeline_helpers)
    result = unittest.TestResult()
    suite.run(result)

    errors = [f"{case.id()}: {error}" for case, error in result.errors]
    failures = [f"{case.id()}: {failure}" for case, failure in result.failures]
    skipped = [f"{case.id()}: {reason}" for case, reason in result.skipped]
    issues = [*errors, *failures]
    return {
        "schema_version": 1,
        "kind": "npu_pipeline_helper_tests",
        "repo_root": str(repo_root),
        "passed": result.wasSuccessful(),
        "errors": issues,
        "warnings": skipped,
        "checks": {
            "tests_run": result.testsRun,
            "error_count": len(errors),
            "failure_count": len(failures),
            "skipped_count": len(skipped),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_tests(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
