#!/usr/bin/env python3
"""Validate NPU pipeline helper documentation/module alignment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_utils import resolve_output_path, write_json_report

EXPECTED_MODULES = (
    "artifact_paths.py",
    "artifact_writer.py",
    "config.py",
    "context_builder.py",
    "fixtures.py",
    "io_utils.py",
    "legacy_compat.py",
    "migration_readiness.py",
    "prompts.py",
    "providers.py",
    "reports.py",
    "runner.py",
    "validators.py",
)

EXPECTED_README_TERMS = (
    "legacy-compatible IO aliases",
    "legacy/new helper equivalence checks",
    "migration readiness reports",
    "common validation report envelopes",
    "runtime-output manifest helpers",
    "NPU/Ollama provider calls",
)


def check_docs(repo_root: Path) -> dict[str, object]:
    package_dir = repo_root / "Tools" / "npu" / "pipeline"
    readme_path = package_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    missing_files = [name for name in EXPECTED_MODULES if not (package_dir / name).exists()]
    missing_terms = [term for term in EXPECTED_README_TERMS if term not in readme]
    undocumented_modules = [
        name
        for name in EXPECTED_MODULES
        if f"`{name.removesuffix('.py')}.py`" not in readme
        and f"`{name.removesuffix('.py')}`" not in readme
    ]

    errors: list[str] = []
    for name in missing_files:
        errors.append(f"missing expected NPU pipeline helper module: {name}")
    for term in missing_terms:
        errors.append(f"README missing expected term: {term}")
    for name in undocumented_modules:
        errors.append(f"README module map missing: {name}")

    return {
        "schema_version": 1,
        "kind": "npu_pipeline_docs",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "checks": {
            "package_dir": str(package_dir),
            "readme_path": str(readme_path),
            "expected_module_count": len(EXPECTED_MODULES),
            "missing_files": missing_files,
            "missing_terms": missing_terms,
            "undocumented_modules": undocumented_modules,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    report = check_docs(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
