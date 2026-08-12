#!/usr/bin/env python3
"""Validate the tool-agnostic artifact domain registry.

This validator makes the domain registry part of the report-only quality gate.
It does not execute providers, run Blender, apply patches or write source files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.artifact_domain_registry import registry_report, validate_registry  # noqa: E402
from Tools.ai.code_patch_plan_common import now_iso, report_only_guardrails, resolve_output_path, write_json_report  # noqa: E402


def build_report(repo_root: Path) -> dict[str, object]:
    """Build the registry validation report."""
    errors, warnings = validate_registry()
    registry = registry_report()
    return {
        "schema_version": 1,
        "kind": "artifact_domain_registry_validation",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "domain_count": registry["domain_count"],
        "domains": [domain["domain"] for domain in registry["domains"]],
        "registry": registry,
        "guardrails": report_only_guardrails(
            registry_static=True,
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
