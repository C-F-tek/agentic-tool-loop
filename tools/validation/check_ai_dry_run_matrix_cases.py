#!/usr/bin/env python3
"""Validate AI dry-run matrix case definitions without running the matrix."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_pipeline_dry_run_matrix import default_cases, default_matrix_workers
except ImportError:  # Allows direct execution from Tools/validation.
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from Tools.ai.run_pipeline_dry_run_matrix import default_cases, default_matrix_workers  # type: ignore


SAFE_CASE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
REQUIRED_FLAGS = {"--dry-run", "--write-dry-run-report"}
GPU_MARKERS = ("gpu", "GPU")
NPU_MARKERS = ("npu", "NPU")


def _has_flag(args: tuple[str, ...], flag: str) -> bool:
    return flag in args


def _arg_after(args: tuple[str, ...], flag: str) -> str | None:
    try:
        index = args.index(flag)
    except ValueError:
        return None
    next_index = index + 1
    if next_index >= len(args):
        return None
    return args[next_index]


def _looks_gpu_related(case: Any) -> bool:
    text = " ".join([case.name, case.purpose, *case.args])
    return any(marker in text for marker in GPU_MARKERS)


def _looks_npu_related(case: Any) -> bool:
    text = " ".join([case.name, case.purpose, *case.args])
    return any(marker in text for marker in NPU_MARKERS)


def validate_cases(min_case_count: int) -> dict[str, Any]:
    """Validate static dry-run matrix case definitions."""
    cases = list(default_cases(None))
    errors: list[str] = []
    warnings: list[str] = []
    names: list[str] = []
    case_summaries: list[dict[str, Any]] = []

    for case in cases:
        names.append(case.name)
        case_errors: list[str] = []
        case_warnings: list[str] = []

        if not SAFE_CASE_NAME_RE.match(case.name):
            case_errors.append("case name must match ^[a-z0-9_]+$")

        for flag in REQUIRED_FLAGS:
            if not _has_flag(case.args, flag):
                case_errors.append(f"missing required flag: {flag}")

        if _has_flag(case.args, "--build-music-summary") and not _has_flag(case.args, "--analysis-json"):
            case_errors.append("--build-music-summary requires --analysis-json even for dry-run preflight")

        if _has_flag(case.args, "--analysis-json"):
            analysis_path = _arg_after(case.args, "--analysis-json")
            if not analysis_path:
                case_errors.append("--analysis-json is missing its value")
            elif "sample_analysis.json" not in analysis_path:
                case_warnings.append("analysis-json path is not the deterministic dry-run sample")

        if _has_flag(case.args, "--gpu-command"):
            gpu_command = _arg_after(case.args, "--gpu-command")
            if not gpu_command:
                case_errors.append("--gpu-command is missing its value")
            elif "dry run" not in gpu_command.lower() and "dry-run" not in gpu_command.lower():
                case_warnings.append("gpu command does not clearly state dry-run intent")

        if _looks_gpu_related(case) and "dry-run" not in case.purpose.lower() and "without executing" not in case.purpose.lower():
            case_warnings.append("GPU-related case purpose should clearly state that no GPU workload executes")

        if _looks_npu_related(case) and "dry-run" not in case.purpose.lower() and "without executing" not in case.purpose.lower() and "planning" not in case.purpose.lower():
            case_warnings.append("NPU-related case purpose should clearly state planning/no-execution intent")

        errors.extend(f"{case.name}: {item}" for item in case_errors)
        warnings.extend(f"{case.name}: {item}" for item in case_warnings)
        case_summaries.append(
            {
                "name": case.name,
                "arg_count": len(case.args),
                "purpose": case.purpose,
                "has_dry_run": _has_flag(case.args, "--dry-run"),
                "has_report": _has_flag(case.args, "--write-dry-run-report"),
                "has_validation": _has_flag(case.args, "--validate"),
                "has_chunks": _has_flag(case.args, "--build-chunks"),
                "has_music_summary": _has_flag(case.args, "--build-music-summary"),
                "has_npu_review": _has_flag(case.args, "--use-npu"),
                "has_gpu_command": _has_flag(case.args, "--gpu-command"),
                "errors": case_errors,
                "warnings": case_warnings,
            }
        )

    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate case names: {', '.join(duplicates)}")

    if len(cases) < min_case_count:
        errors.append(f"case count {len(cases)} is below required minimum {min_case_count}")

    worker_default = default_matrix_workers()
    if worker_default < 1:
        errors.append("default_matrix_workers() returned less than 1")
    if worker_default > 32:
        warnings.append("default matrix worker count is unexpectedly high")

    coverage = {
        "validation_cases": sum(1 for item in case_summaries if item["has_validation"]),
        "chunk_cases": sum(1 for item in case_summaries if item["has_chunks"]),
        "music_summary_cases": sum(1 for item in case_summaries if item["has_music_summary"]),
        "npu_cases": sum(1 for item in case_summaries if item["has_npu_review"]),
        "gpu_cases": sum(1 for item in case_summaries if item["has_gpu_command"]),
    }

    for key, count in coverage.items():
        if count < 1:
            errors.append(f"missing coverage bucket: {key}")

    return {
        "schema_version": 1,
        "kind": "ai_dry_run_matrix_cases",
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "case_count": len(cases),
        "min_case_count": min_case_count,
        "default_matrix_workers": worker_default,
        "coverage": coverage,
        "cases": case_summaries,
        "notes": [
            "This validator checks matrix definitions only; it does not run pipeline cases.",
            "Every case must include --dry-run and --write-dry-run-report.",
            "GPU/NPU cases must remain planned-only in the dry-run matrix.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--min-case-count", type=int, default=20)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = validate_cases(args.min_case_count)
    report["repo_root"] = repo_root.as_posix()

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
