#!/usr/bin/env python3
"""Validate common contracts for generated validation reports."""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


DEFAULT_REPORT_DIR = "output/validation"
REQUIRED_COMMON_FIELDS = ("schema_version", "repo_root", "passed")
RECOMMENDED_COMMON_FIELDS = ("kind", "errors")
NON_REPORT_FILE_PATTERNS = ("*_stdout.json", "*_request_*.json", "*_tool_requests.json")


EXPECTED_REPORT_KINDS = {
    "ai_dry_run_matrix_cases.json": "ai_dry_run_matrix_cases",
    "ai_dry_run_matrix_outputs.json": "ai_dry_run_matrix_outputs",
    "ai_pipeline_report_contract.json": "ai_pipeline_report_contract",
    "generated_python_policy.json": "generated_python_policy",
    "generated_blender_script_policy.json": "generated_blender_script_policy",
    "json_artifacts.json": "json_artifacts",
    "package_structure.json": "package_structure",
    "python_syntax.json": "python_syntax",
}


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, f"not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"read error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def is_report_candidate(path: Path) -> bool:
    return not any(fnmatch.fnmatch(path.name, pattern) for pattern in NON_REPORT_FILE_PATTERNS)


def collect_report_files(report_dir: Path) -> tuple[list[Path], list[Path]]:
    if not report_dir.exists():
        return [], []
    files = sorted(path for path in report_dir.glob("*.json") if path.is_file())
    reports = [path for path in files if is_report_candidate(path)]
    ignored = [path for path in files if not is_report_candidate(path)]
    return reports, ignored


def relative_or_absolute(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def validate_report_file(path: Path, repo_root: Path, require_recommended: bool) -> dict[str, Any]:
    rel = relative_or_absolute(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, load_error = load_json_object(path)
    if load_error:
        return {
            "path": rel,
            "ok": False,
            "errors": [load_error],
            "warnings": warnings,
            "schema_version": None,
            "kind": None,
            "passed": None,
        }

    assert data is not None
    for field in REQUIRED_COMMON_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    for field in RECOMMENDED_COMMON_FIELDS:
        if field not in data:
            message = f"missing recommended field: {field}"
            if require_recommended:
                errors.append(message)
            else:
                warnings.append(message)

    if "schema_version" in data and not isinstance(data["schema_version"], int):
        errors.append("schema_version must be an integer")

    if "repo_root" in data and not isinstance(data["repo_root"], str):
        errors.append("repo_root must be a string")

    if "passed" in data and not isinstance(data["passed"], bool):
        errors.append("passed must be a boolean")

    if "errors" in data and not isinstance(data["errors"], list):
        errors.append("errors must be a list")

    if "warnings" in data and not isinstance(data["warnings"], list):
        errors.append("warnings must be a list when present")

    expected_kind = EXPECTED_REPORT_KINDS.get(path.name)
    if expected_kind and data.get("kind") and data.get("kind") != expected_kind:
        warnings.append(f"kind differs from expected mapping: expected={expected_kind!r} actual={data.get('kind')!r}")

    if data.get("passed") is False and not data.get("errors"):
        warnings.append("passed=false but root errors is empty or missing")

    return {
        "path": rel,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "schema_version": data.get("schema_version"),
        "kind": data.get("kind"),
        "passed": data.get("passed"),
    }


def validate_reports(
    repo_root: Path,
    report_dir: Path,
    require_recommended: bool,
    report_files: list[Path] | None = None,
) -> dict[str, Any]:
    if report_files:
        files = [
            path if path.is_absolute() else repo_root / path
            for path in report_files
        ]
        ignored_files: list[Path] = []
    else:
        files, ignored_files = collect_report_files(report_dir)
    results = [validate_report_file(path, repo_root, require_recommended) for path in files]
    errors: list[str] = []
    warnings: list[str] = []
    for item in results:
        for error in item["errors"]:
            errors.append(f"{item['path']}: {error}")
        for warning in item["warnings"]:
            warnings.append(f"{item['path']}: {warning}")

    if not files:
        errors.append(f"no validation report JSON files found in {relative_or_absolute(report_dir, repo_root)}")

    return {
        "schema_version": 1,
        "kind": "validation_report_contract",
        "repo_root": repo_root.as_posix(),
        "report_dir": relative_or_absolute(report_dir, repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "report_count": len(results),
        "ignored_count": len(ignored_files),
        "ignored_files": [relative_or_absolute(path, repo_root) for path in ignored_files],
        "ignored_patterns": list(NON_REPORT_FILE_PATTERNS),
        "require_recommended": require_recommended,
        "required_common_fields": list(REQUIRED_COMMON_FIELDS),
        "recommended_common_fields": list(RECOMMENDED_COMMON_FIELDS),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--report-file", action="append", default=[], help="Validate only these report JSON files instead of scanning report-dir.")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument(
        "--require-recommended",
        action="store_true",
        help="Treat missing recommended common fields as errors instead of warnings.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = repo_root / report_dir
    report_files = [Path(item) for item in args.report_file]
    report = validate_reports(repo_root, report_dir.resolve(), args.require_recommended, report_files)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
