#!/usr/bin/env python3
"""Validate one AI pipeline schema-v6 report without executing the pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from ai_pipeline_report_contracts import validate_ai_pipeline_report_file
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.ai_pipeline_report_contracts import validate_ai_pipeline_report_file  # type: ignore


def validate_report(repo_root: Path, report_path: Path, require_dry_run: bool) -> dict:
    """Validate one report and return a validation report payload."""
    report_exists = report_path.exists()
    contract = validate_ai_pipeline_report_file(report_path, require_dry_run=require_dry_run)
    return {
        "schema_version": 1,
        "kind": "ai_pipeline_report_contract",
        "repo_root": repo_root.as_posix(),
        "report_path": report_path.as_posix(),
        "report_exists": report_exists,
        "require_dry_run": require_dry_run,
        "passed": contract["passed"],
        "errors": contract["errors"],
        "warnings": contract["warnings"],
        "checks": contract["checks"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--report",
        default="output/ai_pipeline/ai_pipeline_dry_run_report.json",
        help="AI pipeline JSON report path, relative to --repo-root unless absolute.",
    )
    parser.add_argument("--require-dry-run", action="store_true", help="Require report.dry_run=true and planned-only steps.")
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = repo_root / report_path
    report_path = report_path.resolve()

    report = validate_report(repo_root, report_path, args.require_dry_run)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = repo_root / output
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
