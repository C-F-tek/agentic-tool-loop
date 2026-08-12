#!/usr/bin/env python3
"""Validate compact dry-run matrix evidence bundles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_KIND = "dry_run_matrix_evidence_bundle"
REPORT_KIND = "dry_run_matrix_evidence_bundle_validation"
EXPECTED_SCHEMA_VERSION = 1
REQUIRED_DECISIONS = (
    "matrix_passed",
    "all_validation_reports_passed",
    "all_case_reports_present",
    "all_cases_dry_run",
    "all_steps_planned_only",
    "provider_execution_seen",
    "gpu_npu_workloads_executed",
    "parallel_execution_seen",
    "repeat_cases_seen",
)
REQUIRED_VALIDATION_KINDS = {
    "ai_dry_run_matrix_cases",
    "ai_dry_run_matrix_contract",
    "ai_dry_run_matrix_outputs",
    "generated_artifact_path_policy",
}

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a stable repo-relative POSIX path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load a JSON object from path."""
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


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    """Resolve value under repo_root unless already absolute."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def split_path_values(items: list[str]) -> list[str]:
    """Split comma-separated path CLI values."""
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate one compact dry-run matrix evidence bundle."""
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    rel_path = repo_relative(path, repo_root)
    if data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "passed": False,
            "kind": None,
            "case_count": None,
            "errors": [parse_error] if parse_error else ["failed to read evidence"],
            "warnings": warnings,
        }

    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("passed") is not True:
        errors.append("evidence passed must be true")
    if data.get("errors") not in ([], None):
        errors.append("evidence errors must be empty")
    if not isinstance(data.get("source_matrix_report"), str) or not data.get("source_matrix_report"):
        errors.append("source_matrix_report must be a non-empty string")

    matrix = data.get("matrix")
    if not isinstance(matrix, dict):
        errors.append("matrix must be an object")
        matrix = {}
    else:
        if matrix.get("passed") is not True:
            errors.append("matrix.passed must be true")
        if not _is_positive_int(matrix.get("case_count")):
            errors.append("matrix.case_count must be int > 0")
        if not _is_positive_int(matrix.get("planned_case_count")):
            errors.append("matrix.planned_case_count must be int > 0")
        if not _is_positive_int(matrix.get("base_case_count")):
            errors.append("matrix.base_case_count must be int > 0")
        if not _is_positive_int(matrix.get("repeat_cases")):
            errors.append("matrix.repeat_cases must be int > 0")
        if not _is_positive_int(matrix.get("matrix_workers")):
            errors.append("matrix.matrix_workers must be int > 0")
        if matrix.get("failed_case_count") != 0:
            errors.append("matrix.failed_case_count must be 0")
        if matrix.get("non_planned_case_count") != 0:
            errors.append("matrix.non_planned_case_count must be 0")

    summary = data.get("case_summary")
    if not isinstance(summary, dict):
        errors.append("case_summary must be an object")
        summary = {}
    else:
        case_count = summary.get("case_count")
        if not _is_positive_int(case_count):
            errors.append("case_summary.case_count must be int > 0")
        for key in (
            "report_count",
            "dry_run_count",
            "planned_only_count",
            "validation_case_count",
            "chunk_case_count",
            "music_summary_case_count",
            "npu_planning_case_count",
            "gpu_planning_case_count",
        ):
            if not _is_non_negative_int(summary.get(key)):
                errors.append(f"case_summary.{key} must be int >= 0")
        if _is_positive_int(case_count):
            for key in ("report_count", "dry_run_count", "planned_only_count"):
                if summary.get(key) != case_count:
                    errors.append(f"case_summary.{key} must equal case_count")
            if matrix.get("case_count") != case_count:
                errors.append("matrix.case_count must equal case_summary.case_count")
            if matrix.get("result_count") != case_count:
                errors.append("matrix.result_count must equal case_summary.case_count")
        for coverage_key in ("validation_case_count", "chunk_case_count", "music_summary_case_count", "npu_planning_case_count", "gpu_planning_case_count"):
            if summary.get(coverage_key) == 0:
                errors.append(f"case_summary.{coverage_key} must be greater than 0 for baseline coverage")

    validations = data.get("validation_reports")
    validation_kinds: set[str] = set()
    if not isinstance(validations, list) or not validations:
        errors.append("validation_reports must be a non-empty list")
    else:
        for index, item in enumerate(validations):
            if not isinstance(item, dict):
                errors.append(f"validation_reports[{index}] must be an object")
                continue
            kind = item.get("kind")
            if isinstance(kind, str):
                validation_kinds.add(kind)
            if item.get("exists") is not True:
                errors.append(f"validation_reports[{index}].exists must be true")
            if item.get("json_ok") is not True:
                errors.append(f"validation_reports[{index}].json_ok must be true")
            if item.get("passed") is not True:
                errors.append(f"validation_reports[{index}].passed must be true")
        missing = sorted(REQUIRED_VALIDATION_KINDS - validation_kinds)
        if missing:
            errors.append(f"validation_reports missing kinds: {', '.join(missing)}")

    decisions = data.get("decision")
    if not isinstance(decisions, dict):
        errors.append("decision must be an object")
        decisions = {}
    else:
        for key in REQUIRED_DECISIONS:
            if key not in decisions:
                errors.append(f"decision.{key} missing")
        for key in (
            "matrix_passed",
            "all_validation_reports_passed",
            "all_case_reports_present",
            "all_cases_dry_run",
            "all_steps_planned_only",
        ):
            if decisions.get(key) is not True:
                errors.append(f"decision.{key} must be true")
        if decisions.get("provider_execution_seen") is not False:
            errors.append("decision.provider_execution_seen must be false")
        if decisions.get("gpu_npu_workloads_executed") is not False:
            errors.append("decision.gpu_npu_workloads_executed must be false")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
        cases = []
    else:
        names: list[str] = []
        for index, item in enumerate(cases):
            if not isinstance(item, dict):
                errors.append(f"cases[{index}] must be an object")
                continue
            name = item.get("name")
            if isinstance(name, str):
                names.append(name)
            else:
                errors.append(f"cases[{index}].name must be a string")
            if item.get("returncode") != 0:
                errors.append(f"cases[{index}].returncode must be 0")
            if item.get("report_exists") is not True:
                errors.append(f"cases[{index}].report_exists must be true")
            if item.get("report_json_ok") is not True:
                errors.append(f"cases[{index}].report_json_ok must be true")
            if item.get("report_passed") is not True:
                errors.append(f"cases[{index}].report_passed must be true")
            if item.get("dry_run") is not True:
                errors.append(f"cases[{index}].dry_run must be true")
            if item.get("all_steps_planned_only") is not True:
                errors.append(f"cases[{index}].all_steps_planned_only must be true")
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            errors.append(f"duplicate case names: {', '.join(duplicates)}")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "passed": not errors,
        "kind": data.get("kind"),
        "case_count": summary.get("case_count") if isinstance(summary, dict) else None,
        "matrix_workers": matrix.get("matrix_workers") if isinstance(matrix, dict) else None,
        "repeat_cases": matrix.get("repeat_cases") if isinstance(matrix, dict) else None,
        "validation_kinds": sorted(validation_kinds),
        "errors": errors,
        "warnings": warnings,
    }


def default_evidence_paths(repo_root: Path) -> list[Path]:
    """Return default dry-run matrix evidence paths under docs evidence."""
    evidence_dir = repo_root / "docs" / "LOCAL_VALIDATION_EVIDENCE"
    paths: list[Path] = []
    for path in sorted(evidence_dir.glob("*.json")):
        data, parse_error = read_json_object(path)
        if parse_error or data is None or data.get("kind") == EXPECTED_KIND:
            paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--evidence", action="append", default=[], help="Evidence JSON path. Repeatable or comma-separated.")
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    evidence_values = split_path_values(args.evidence)
    evidence_paths = (
        [resolve_repo_path(repo_root, value) for value in evidence_values]
        if evidence_values
        else default_evidence_paths(repo_root)
    )
    results = [validate_evidence(path, repo_root) for path in evidence_paths]
    errors = [
        f"{item['path']}: {error}"
        for item in results
        for error in item.get("errors", [])
    ]
    warnings = [
        f"{item['path']}: {warning}"
        for item in results
        for warning in item.get("warnings", [])
    ]
    if not evidence_paths:
        errors.append("no dry-run matrix evidence bundles found")

    report = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence_count": len(evidence_paths),
        "results": results,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = resolve_output_path(repo_root, args.output)
        write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
