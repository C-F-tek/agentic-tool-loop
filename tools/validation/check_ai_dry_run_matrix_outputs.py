#!/usr/bin/env python3
"""Validate consistency between the dry-run matrix report and per-case reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_MATRIX_FIELDS = {
    "schema_version",
    "repo_root",
    "output_dir",
    "case_count",
    "planned_case_count",
    "matrix_workers",
    "passed",
    "results",
}

REQUIRED_CASE_REPORT_FIELDS = {
    "schema_version",
    "repo_root",
    "output_dir",
    "dry_run",
    "passed",
    "preflight",
    "step_count",
    "summary",
    "schedule",
    "steps",
}


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load a JSON object from path."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"read error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def _as_path(repo_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def validate_outputs(repo_root: Path, matrix_report: Path) -> dict[str, Any]:
    """Validate matrix output consistency without rerunning any pipeline step."""
    errors: list[str] = []
    warnings: list[str] = []
    case_summaries: list[dict[str, Any]] = []

    matrix, load_error = load_json(matrix_report)
    if load_error:
        return {
            "schema_version": 1,
            "kind": "ai_dry_run_matrix_outputs",
            "repo_root": repo_root.as_posix(),
            "matrix_report": matrix_report.as_posix(),
            "passed": False,
            "errors": [load_error],
            "warnings": warnings,
            "case_count": 0,
            "cases": [],
        }

    missing_matrix_fields = sorted(REQUIRED_MATRIX_FIELDS - set(matrix))
    if missing_matrix_fields:
        errors.append(f"matrix report missing fields: {', '.join(missing_matrix_fields)}")

    results = matrix.get("results")
    if not isinstance(results, list):
        errors.append("matrix report field results must be a list")
        results = []

    declared_case_count = matrix.get("case_count")
    if declared_case_count != len(results):
        errors.append(f"case_count mismatch: declared={declared_case_count!r} actual={len(results)}")

    planned_case_count = matrix.get("planned_case_count")
    if isinstance(planned_case_count, int) and planned_case_count < len(results):
        errors.append(f"planned_case_count {planned_case_count} is below actual result count {len(results)}")

    names = [str(item.get("name")) for item in results if isinstance(item, dict)]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate result names: {', '.join(duplicates)}")

    matrix_output_dir = _as_path(repo_root, str(matrix.get("output_dir"))) if matrix.get("output_dir") else None
    if matrix_output_dir and not matrix_output_dir.exists():
        warnings.append(f"matrix output_dir does not exist: {matrix_output_dir}")

    for index, item in enumerate(results):
        if not isinstance(item, dict):
            errors.append(f"results[{index}] is not an object")
            continue
        name = str(item.get("name") or f"case_{index}")
        report_path = _as_path(repo_root, item.get("report_path"))
        case_errors: list[str] = []
        case_warnings: list[str] = []
        case_report: dict[str, Any] | None = None

        if report_path is None:
            case_errors.append("missing report_path")
        else:
            case_report, case_load_error = load_json(report_path)
            if case_load_error:
                case_errors.append(case_load_error)

        if case_report is not None:
            missing_case_fields = sorted(REQUIRED_CASE_REPORT_FIELDS - set(case_report))
            if missing_case_fields:
                case_errors.append(f"case report missing fields: {', '.join(missing_case_fields)}")

            if case_report.get("dry_run") is not True:
                case_errors.append("case report dry_run is not true")

            if item.get("report_passed") != case_report.get("passed"):
                case_errors.append(
                    f"report_passed mismatch: matrix={item.get('report_passed')!r} case={case_report.get('passed')!r}"
                )

            if item.get("step_count") != case_report.get("step_count"):
                case_errors.append(
                    f"step_count mismatch: matrix={item.get('step_count')!r} case={case_report.get('step_count')!r}"
                )

            if item.get("lanes") != case_report.get("lanes"):
                case_errors.append("lanes mismatch between matrix result and case report")

            if item.get("summary") != case_report.get("summary"):
                case_errors.append("summary mismatch between matrix result and case report")

            if item.get("schedule") != case_report.get("schedule"):
                case_errors.append("schedule mismatch between matrix result and case report")

            preflight = case_report.get("preflight")
            if isinstance(preflight, dict) and preflight.get("errors"):
                case_warnings.append(f"preflight errors present: {preflight.get('errors')}")

            steps = case_report.get("steps")
            if isinstance(steps, list):
                planned_only_count = sum(1 for step in steps if isinstance(step, dict) and step.get("planned_only") is True)
                if planned_only_count != len(steps):
                    case_errors.append("not all case report steps are planned_only")
            else:
                case_errors.append("case report steps is not a list")

        errors.extend(f"{name}: {error}" for error in case_errors)
        warnings.extend(f"{name}: {warning}" for warning in case_warnings)
        case_summaries.append(
            {
                "name": name,
                "report_path": str(report_path) if report_path else None,
                "report_exists": bool(report_path and report_path.exists()),
                "returncode": item.get("returncode"),
                "report_passed": item.get("report_passed"),
                "step_count": item.get("step_count"),
                "errors": case_errors,
                "warnings": case_warnings,
            }
        )

    if matrix.get("passed") is True:
        failed_cases = [case for case in case_summaries if case["errors"] or case["returncode"] != 0 or case["report_passed"] is not True]
        if failed_cases:
            errors.append("matrix passed=true but at least one case has errors, non-zero returncode or report_passed!=true")

    return {
        "schema_version": 1,
        "kind": "ai_dry_run_matrix_outputs",
        "repo_root": repo_root.as_posix(),
        "matrix_report": matrix_report.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "case_count": len(case_summaries),
        "matrix_workers": matrix.get("matrix_workers"),
        "repeat_cases": matrix.get("repeat_cases"),
        "planned_case_count": matrix.get("planned_case_count"),
        "cases": case_summaries,
        "notes": [
            "This validator checks already generated dry-run matrix outputs; it does not run pipeline cases.",
            "Every per-case report must remain dry_run=true and planned_only for all steps.",
            "Matrix summary fields must match the per-case report payloads.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--matrix-report", default="output/ai_pipeline/dry_run_matrix_report.json")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    matrix_report = Path(args.matrix_report)
    if not matrix_report.is_absolute():
        matrix_report = repo_root / matrix_report
    matrix_report = matrix_report.resolve()

    report = validate_outputs(repo_root, matrix_report)
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
