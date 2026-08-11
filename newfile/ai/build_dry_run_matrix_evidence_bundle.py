#!/usr/bin/env python3
"""Build compact evidence for AI pipeline dry-run matrix reports.

The dry-run matrix writes long local reports under ignored ``output/`` paths.
This helper summarizes those local reports into a Git-trackable evidence bundle
under ``docs/LOCAL_VALIDATION_EVIDENCE/``. It does not execute providers, apply
patches, run Blender, run FFmpeg or start GPU/NPU workloads.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

EVIDENCE_KIND = "dry_run_matrix_evidence_bundle"
DEFAULT_MATRIX_REPORT = "output/ai_pipeline/dry_run_matrix_report.json"
DEFAULT_OUTPUT_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"
DEFAULT_VALIDATION_REPORTS = (
    "output/validation/ai_dry_run_matrix_cases.json",
    "output/validation/ai_dry_run_matrix_contract.json",
    "output/validation/ai_dry_run_matrix_outputs.json",
    "output/validation/generated_artifact_path_policy_from_matrix.json",
)


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a stable repo-relative POSIX path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    """Resolve value under repo_root unless already absolute."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON object from path."""
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


def compact(value: Any, *, max_string: int = 240, max_items: int = 20) -> Any:
    """Return a JSON-safe compact copy of value."""
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "...[truncated]"
    if isinstance(value, list):
        return [compact(item, max_string=max_string, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        return {
            str(key): compact(item, max_string=max_string, max_items=max_items)
            for key, item in value.items()
        }
    return value


def summarize_validation_report(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize one validation report without reading ignored report payloads by inference."""
    data, error = read_json_object(path)
    if data is None:
        return {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": False,
            "kind": None,
            "passed": None,
            "errors": [error] if error else [],
            "warnings": [],
        }
    return {
        "path": repo_relative(path, repo_root),
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "errors": compact(data.get("errors") or [], max_string=300),
        "warnings": compact(data.get("warnings") or [], max_string=300),
        "checks": compact(data.get("checks") or {}, max_string=300),
        "case_count": data.get("case_count"),
        "matrix_workers": data.get("matrix_workers"),
        "repeat_cases": data.get("repeat_cases"),
        "planned_case_count": data.get("planned_case_count"),
    }


def _case_report_path(repo_root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def summarize_case_result(repo_root: Path, item: dict[str, Any], index: int) -> dict[str, Any]:
    """Summarize one matrix result and its per-case dry-run report when present."""
    report_path = _case_report_path(repo_root, item.get("report_path"))
    case_report: dict[str, Any] | None = None
    parse_error: str | None = None
    if report_path is not None:
        case_report, parse_error = read_json_object(report_path)

    steps = case_report.get("steps") if isinstance(case_report, dict) else None
    step_count = len(steps) if isinstance(steps, list) else item.get("step_count")
    planned_only_count = (
        sum(1 for step in steps if isinstance(step, dict) and step.get("planned_only") is True)
        if isinstance(steps, list)
        else None
    )
    lanes = item.get("lanes") if isinstance(item.get("lanes"), dict) else {}
    summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
    name = str(item.get("name") or f"case_{index}")
    command = item.get("command")
    command_text = " ".join(command) if isinstance(command, list) else ""

    return {
        "index": index,
        "name": name,
        "purpose": item.get("purpose"),
        "returncode": item.get("returncode"),
        "duration_sec": item.get("duration_sec"),
        "report_path": repo_relative(report_path, repo_root) if report_path else None,
        "report_exists": bool(report_path and report_path.exists()),
        "report_json_ok": case_report is not None,
        "report_parse_error": parse_error,
        "report_passed": item.get("report_passed"),
        "dry_run": case_report.get("dry_run") if isinstance(case_report, dict) else None,
        "step_count": step_count,
        "planned_only_count": planned_only_count,
        "all_steps_planned_only": (
            planned_only_count == len(steps)
            if isinstance(steps, list)
            else None
        ),
        "has_validation": "--validate" in command_text,
        "has_chunks": "--build-chunks" in command_text,
        "has_music_summary": "--build-music-summary" in command_text,
        "has_npu_planning": "--use-npu" in command_text or "npu" in name.lower(),
        "has_gpu_planning": "--gpu-command" in command_text or "gpu" in name.lower(),
        "lane_keys": sorted(str(key) for key in lanes),
        "summary_keys": sorted(str(key) for key in summary),
    }


def summarize_matrix_report(repo_root: Path, matrix_report: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Summarize matrix and per-case reports."""
    errors: list[str] = []
    data, error = read_json_object(matrix_report)
    if data is None:
        return (
            {
                "path": repo_relative(matrix_report, repo_root),
                "exists": matrix_report.exists(),
                "json_ok": False,
                "parse_error": error,
            },
            [],
            [error or f"failed to read matrix report: {matrix_report}"],
        )

    results = data.get("results")
    if not isinstance(results, list):
        errors.append("matrix report results must be a list")
        results = []

    cases = [
        summarize_case_result(repo_root, item, index)
        for index, item in enumerate(results)
        if isinstance(item, dict)
    ]
    failed_cases = [
        item["name"]
        for item in cases
        if item.get("returncode") != 0 or item.get("report_passed") is not True or item.get("dry_run") is not True
    ]
    non_planned_cases = [
        item["name"]
        for item in cases
        if item.get("all_steps_planned_only") is not True
    ]
    matrix = {
        "path": repo_relative(matrix_report, repo_root),
        "exists": True,
        "json_ok": True,
        "schema_version": data.get("schema_version"),
        "repo_root": data.get("repo_root"),
        "output_dir": data.get("output_dir"),
        "markdown_output": data.get("markdown_output"),
        "passed": data.get("passed"),
        "case_count": data.get("case_count"),
        "planned_case_count": data.get("planned_case_count"),
        "base_case_count": data.get("base_case_count"),
        "repeat_cases": data.get("repeat_cases"),
        "matrix_workers": data.get("matrix_workers"),
        "result_count": len(cases),
        "failed_case_count": len(failed_cases),
        "non_planned_case_count": len(non_planned_cases),
    }
    if failed_cases:
        errors.append(f"failed dry-run cases: {', '.join(failed_cases)}")
    if non_planned_cases:
        errors.append(f"non planned-only cases: {', '.join(non_planned_cases)}")
    return matrix, cases, errors


def build_evidence(
    *,
    repo_root: Path,
    matrix_report: Path,
    validation_reports: list[Path],
    basename: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Build and write the compact evidence bundle."""
    matrix, cases, errors = summarize_matrix_report(repo_root, matrix_report)
    validations = [summarize_validation_report(path, repo_root) for path in validation_reports]
    errors.extend(
        f"{item['path']}: validation report did not pass"
        for item in validations
        if item.get("passed") is not True
    )

    case_count = len(cases)
    report_count = sum(1 for item in cases if item.get("report_exists") is True)
    dry_run_count = sum(1 for item in cases if item.get("dry_run") is True)
    planned_only_count = sum(1 for item in cases if item.get("all_steps_planned_only") is True)
    validation_case_count = sum(1 for item in cases if item.get("has_validation") is True)
    chunk_case_count = sum(1 for item in cases if item.get("has_chunks") is True)
    music_summary_case_count = sum(1 for item in cases if item.get("has_music_summary") is True)
    npu_planning_case_count = sum(1 for item in cases if item.get("has_npu_planning") is True)
    gpu_planning_case_count = sum(1 for item in cases if item.get("has_gpu_planning") is True)

    evidence = {
        "schema_version": 1,
        "kind": EVIDENCE_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "source_matrix_report": matrix.get("path"),
        "source_validation_reports": [item["path"] for item in validations],
        "provider_execution_performed": False,
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "matrix": matrix,
        "validation_reports": validations,
        "case_summary": {
            "case_count": case_count,
            "report_count": report_count,
            "dry_run_count": dry_run_count,
            "planned_only_count": planned_only_count,
            "validation_case_count": validation_case_count,
            "chunk_case_count": chunk_case_count,
            "music_summary_case_count": music_summary_case_count,
            "npu_planning_case_count": npu_planning_case_count,
            "gpu_planning_case_count": gpu_planning_case_count,
        },
        "cases": cases,
        "decision": {
            "matrix_passed": matrix.get("passed") is True,
            "all_validation_reports_passed": all(item.get("passed") is True for item in validations),
            "all_case_reports_present": case_count > 0 and report_count == case_count,
            "all_cases_dry_run": case_count > 0 and dry_run_count == case_count,
            "all_steps_planned_only": case_count > 0 and planned_only_count == case_count,
            "provider_execution_seen": False,
            "gpu_npu_workloads_executed": False,
            "parallel_execution_seen": isinstance(matrix.get("matrix_workers"), int) and matrix.get("matrix_workers", 0) > 1,
            "repeat_cases_seen": isinstance(matrix.get("repeat_cases"), int) and matrix.get("repeat_cases", 0) > 1,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    evidence["evidence_json"] = repo_relative(json_path, repo_root)
    evidence["evidence_markdown"] = repo_relative(md_path, repo_root)
    json_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(evidence), encoding="utf-8")
    return evidence


def render_markdown(evidence: dict[str, Any]) -> str:
    """Render a compact Markdown companion for the evidence bundle."""
    matrix = evidence.get("matrix") if isinstance(evidence.get("matrix"), dict) else {}
    decision = evidence.get("decision") if isinstance(evidence.get("decision"), dict) else {}
    summary = evidence.get("case_summary") if isinstance(evidence.get("case_summary"), dict) else {}
    lines = ["# AI Pipeline Dry-Run Matrix Evidence", ""]
    lines.append(f"- Generated at: `{evidence['generated_at']}`")
    lines.append(f"- Kind: `{evidence['kind']}`")
    lines.append(f"- Passed: `{evidence['passed']}`")
    lines.append(f"- Provider execution performed: `{evidence['provider_execution_performed']}`")
    lines.append(f"- Matrix report: `{evidence['source_matrix_report']}`")
    lines.append(f"- Matrix workers: `{matrix.get('matrix_workers')}`")
    lines.append(f"- Repeat cases: `{matrix.get('repeat_cases')}`")
    lines.append(f"- Cases: `{summary.get('case_count')}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for key, value in decision.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Case Summary")
    lines.append("")
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Validation Reports")
    lines.append("")
    for item in evidence.get("validation_reports", []):
        lines.append(f"- `{item.get('path')}`: passed `{item.get('passed')}`, kind `{item.get('kind')}`")
    lines.append("")
    lines.append("## Failed Cases")
    lines.append("")
    failed = [
        item.get("name")
        for item in evidence.get("cases", [])
        if item.get("returncode") != 0 or item.get("report_passed") is not True or item.get("dry_run") is not True
    ]
    if failed:
        for name in failed:
            lines.append(f"- `{name}`")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("This evidence summarizes dry-run planning only. It is not provider execution proof.")
    return "\n".join(lines) + "\n"


def split_path_values(items: list[str]) -> list[str]:
    """Split comma-separated path CLI values."""
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--matrix-report", default=DEFAULT_MATRIX_REPORT)
    parser.add_argument("--validation-report", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default="ai_pipeline_dry_run_matrix_evidence")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    matrix_report = resolve_repo_path(repo_root, args.matrix_report)
    validation_values = split_path_values(args.validation_report) or list(DEFAULT_VALIDATION_REPORTS)
    validation_reports = [resolve_repo_path(repo_root, item) for item in validation_values]
    output_dir = resolve_repo_path(repo_root, args.output_dir)

    evidence = build_evidence(
        repo_root=repo_root,
        matrix_report=matrix_report,
        validation_reports=validation_reports,
        basename=args.basename,
        output_dir=output_dir,
    )
    print(
        json.dumps(
            {
                "passed": evidence["passed"],
                "kind": evidence["kind"],
                "evidence_json": evidence["evidence_json"],
                "evidence_markdown": evidence["evidence_markdown"],
                "case_count": evidence["case_summary"]["case_count"],
                "matrix_workers": evidence["matrix"].get("matrix_workers"),
                "repeat_cases": evidence["matrix"].get("repeat_cases"),
                "provider_execution_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if evidence["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
