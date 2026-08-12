#!/usr/bin/env python3
"""Run a matrix of safe dry-run checks for the AI artifact pipeline.

The matrix invokes ``Tools/ai/run_parallel_artifact_pipeline.py`` with several
non-invasive configurations and writes compact JSON and Markdown summaries.
It does not run NPU/GPU/Blender workloads because every invocation includes
``--dry-run``.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from pipeline.markdown_report import write_dry_run_matrix_markdown
except ImportError:  # Allows package-style imports during external checks.
    from Tools.ai.pipeline.markdown_report import write_dry_run_matrix_markdown  # type: ignore


@dataclass(frozen=True)
class MatrixCase:
    name: str
    args: tuple[str, ...]
    purpose: str


def default_matrix_workers() -> int:
    """Return a conservative default for matrix-level parallel dry-run execution."""
    cpu_count = os.cpu_count() or 1
    return max(1, min(8, cpu_count))


def _planned_gpu_command() -> str:
    """Return a harmless command string used only for dry-run GPU planning."""
    return "python -c \"print('gpu planner dry run only')\""


def _planned_gpu_placeholder_command() -> str:
    """Return a harmless placeholder-aware GPU command used only for dry-run planning."""
    return "python -c \"import sys; print('gpu placeholder dry run only'); print(sys.argv[1]); print(sys.argv[2])\" {brief} {output}"


def ensure_sample_analysis_json(repo_root: Path) -> Path:
    """Create a tiny deterministic analysis JSON so music-summary dry-runs pass preflight."""
    sample = repo_root / "output" / "ai_pipeline" / "dry_run_matrix_inputs" / "sample_analysis.json"
    sample.parent.mkdir(parents=True, exist_ok=True)
    if not sample.exists():
        payload = {
            "schema_version": 1,
            "source": "dry_run_matrix_sample",
            "duration_sec": 1.0,
            "sample_rate": 44100,
            "bpm": 120.0,
            "segments": [
                {
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "label": "dry_run_sample",
                    "energy": 0.5,
                }
            ],
            "notes": [
                "Synthetic sample used only to satisfy preflight during dry-run matrix planning.",
                "Do not treat this as real audio analysis output.",
            ],
        }
        sample.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sample


def repeat_cases(cases: tuple[MatrixCase, ...], repeat_count: int) -> tuple[MatrixCase, ...]:
    """Repeat matrix cases for stress testing while keeping output directories unique."""
    repeat_count = max(1, repeat_count)
    if repeat_count == 1:
        return cases
    repeated: list[MatrixCase] = []
    for round_index in range(1, repeat_count + 1):
        suffix = f"_r{round_index:02d}"
        for case in cases:
            repeated.append(
                MatrixCase(
                    name=f"{case.name}{suffix}",
                    args=case.args,
                    purpose=f"Repeat {round_index}/{repeat_count}: {case.purpose}",
                )
            )
    return tuple(repeated)


def default_cases(repo_root: Path | None = None) -> tuple[MatrixCase, ...]:
    agent_state_packet = None
    sample_analysis_json = Path("output/ai_pipeline/dry_run_matrix_inputs/sample_analysis.json")
    if repo_root is not None:
        candidate = repo_root / "output" / "ai_pipeline" / "agent_state" / "validate_agent_state_memory_integration_plan.json"
        if candidate.exists():
            agent_state_packet = candidate
        sample_analysis_json = ensure_sample_analysis_json(repo_root)

    cases = [
        MatrixCase(
            name="base",
            args=("--dry-run", "--write-dry-run-report"),
            purpose="Default safe dry-run with guardrail and smart context enabled.",
        ),
        MatrixCase(
            name="no_auto_remediation",
            args=("--dry-run", "--write-dry-run-report", "--no-guardrail-auto-remediate"),
            purpose="Verify pipeline without automatic guardrail remediation passes.",
        ),
        MatrixCase(
            name="no_npu_guardrail",
            args=("--dry-run", "--write-dry-run-report", "--no-npu-guardrail"),
            purpose="Verify dry-run planning when NPU guardrail is disabled without executing NPU workloads.",
        ),
        MatrixCase(
            name="no_smart_context",
            args=("--dry-run", "--write-dry-run-report", "--no-smart-context"),
            purpose="Verify planning when smart context is disabled and guardrail input falls back to the output directory.",
        ),
        MatrixCase(
            name="no_wave_review",
            args=("--dry-run", "--write-dry-run-report", "--no-review-wave-entrypoints"),
            purpose="Verify planning when first-wave WAV entrypoint review is disabled.",
        ),
        MatrixCase(
            name="minimal_no_context_no_guardrail",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--no-review-wave-entrypoints",
                "--no-smart-context",
                "--no-npu-guardrail",
            ),
            purpose="Verify the smallest no-op planning shape remains reportable.",
        ),
        MatrixCase(
            name="with_validation",
            args=("--dry-run", "--write-dry-run-report", "--validate"),
            purpose="Verify validate_ai_artifacts stage planning.",
        ),
        MatrixCase(
            name="validation_no_guardrail",
            args=("--dry-run", "--write-dry-run-report", "--validate", "--no-npu-guardrail"),
            purpose="Verify validation planning when NPU guardrail is disabled.",
        ),
        MatrixCase(
            name="with_chunks",
            args=("--dry-run", "--write-dry-run-report", "--build-chunks"),
            purpose="Verify semantic code chunk stage planning.",
        ),
        MatrixCase(
            name="chunks_no_smart_context",
            args=("--dry-run", "--write-dry-run-report", "--build-chunks", "--no-smart-context"),
            purpose="Verify chunk planning without smart context.",
        ),
        MatrixCase(
            name="with_music_summary_planned",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
            ),
            purpose="Verify music intermediate stage planning using a deterministic synthetic analysis JSON.",
        ),
        MatrixCase(
            name="music_no_smart_context",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
                "--no-smart-context",
            ),
            purpose="Verify music intermediate planning when smart context is disabled.",
        ),
        MatrixCase(
            name="smart_context_tiny_budget",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--smart-max-packet-chars",
                "512",
                "--smart-max-capsule-chars",
                "128",
            ),
            purpose="Verify smart-context planning with a tiny packet/capsule budget.",
        ),
        MatrixCase(
            name="smart_context_small_budget",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--smart-max-packet-chars",
                "2048",
                "--smart-max-capsule-chars",
                "512",
            ),
            purpose="Verify smart-context planning with a small packet/capsule budget.",
        ),
        MatrixCase(
            name="smart_context_large_budget",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--smart-max-packet-chars",
                "64000",
                "--smart-max-capsule-chars",
                "8192",
            ),
            purpose="Verify smart-context planning with a larger packet/capsule budget.",
        ),
        MatrixCase(
            name="custom_track_stem_ascii",
            args=("--dry-run", "--write-dry-run-report", "--track-stem", "dry_run_track_120bpm"),
            purpose="Verify planning with a custom ASCII track stem.",
        ),
        MatrixCase(
            name="custom_track_stem_spaces",
            args=("--dry-run", "--write-dry-run-report", "--track-stem", "Dry Run Track With Spaces"),
            purpose="Verify slug/path planning with spaces in track stem.",
        ),
        MatrixCase(
            name="custom_track_stem_symbols",
            args=("--dry-run", "--write-dry-run-report", "--track-stem", "Dry_Run-Track_120 BPM!"),
            purpose="Verify slug/path planning with punctuation in track stem.",
        ),
        MatrixCase(
            name="custom_smart_task_short",
            args=("--dry-run", "--write-dry-run-report", "--smart-task", "dry-run short planning task"),
            purpose="Verify planning with a short custom smart-context task.",
        ),
        MatrixCase(
            name="custom_smart_task_multiclause",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--smart-task",
                "dry-run plan: preserve audio timing; review generated paths; keep runtime packages unchanged",
            ),
            purpose="Verify planning with a multi-clause custom smart-context task.",
        ),
        MatrixCase(
            name="guardrail_max_passes_zero",
            args=("--dry-run", "--write-dry-run-report", "--guardrail-max-passes", "0"),
            purpose="Verify report planning when guardrail remediation max passes is zero.",
        ),
        MatrixCase(
            name="guardrail_max_passes_one_no_auto",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--guardrail-max-passes",
                "1",
                "--no-guardrail-auto-remediate",
            ),
            purpose="Verify guardrail planning with one max pass and auto-remediation disabled.",
        ),
        MatrixCase(
            name="guardrail_max_passes_four",
            args=("--dry-run", "--write-dry-run-report", "--guardrail-max-passes", "4"),
            purpose="Verify report planning with a larger remediation pass budget.",
        ),
        MatrixCase(
            name="continue_on_error_planned",
            args=("--dry-run", "--write-dry-run-report", "--continue-on-error"),
            purpose="Verify inner pipeline continue-on-error planning remains reportable.",
        ),
        MatrixCase(
            name="with_npu_review_workers_1",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--npu-workers", "1"),
            purpose="Verify optional NPU artifact review stage planning with one worker and no NPU execution.",
        ),
        MatrixCase(
            name="with_npu_review_workers_4",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--npu-workers", "4"),
            purpose="Verify optional NPU artifact review stage planning with the recommended local worker cap.",
        ),
        MatrixCase(
            name="with_npu_review_workers_8_warning",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--npu-workers", "8"),
            purpose="Verify high NPU worker planning emits warnings without executing NPU workloads.",
        ),
        MatrixCase(
            name="with_npu_review_workers_16_warning",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--npu-workers", "16"),
            purpose="Verify very high NPU worker planning emits warnings without executing NPU workloads.",
        ),
        MatrixCase(
            name="npu_review_without_guardrail",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--no-npu-guardrail"),
            purpose="Verify NPU review planning when NPU guardrail is disabled.",
        ),
        MatrixCase(
            name="npu_review_no_smart_context",
            args=("--dry-run", "--write-dry-run-report", "--use-npu", "--no-smart-context"),
            purpose="Verify NPU review planning with smart context disabled.",
        ),
        MatrixCase(
            name="with_gpu_command_planned",
            args=("--dry-run", "--write-dry-run-report", "--gpu-command", _planned_gpu_command()),
            purpose="Verify optional GPU command planning without executing GPU workloads.",
        ),
        MatrixCase(
            name="with_gpu_placeholder_command_planned",
            args=("--dry-run", "--write-dry-run-report", "--gpu-command", _planned_gpu_placeholder_command()),
            purpose="Verify GPU command placeholder formatting for {brief} and {output} without executing GPU workloads.",
        ),
        MatrixCase(
            name="gpu_command_missing_output_warning",
            args=("--dry-run", "--write-dry-run-report", "--gpu-command", "python -c \"print('gpu dry run without output placeholder')\" {brief}"),
            purpose="Verify GPU command warning when {output} placeholder is missing without executing GPU workloads.",
        ),
        MatrixCase(
            name="gpu_command_missing_brief_warning",
            args=("--dry-run", "--write-dry-run-report", "--gpu-command", "python -c \"print('gpu dry run without brief placeholder')\" {output}"),
            purpose="Verify GPU command warning when {brief} placeholder is missing without executing GPU workloads.",
        ),
        MatrixCase(
            name="validation_chunks_music",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--validate",
                "--build-chunks",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
            ),
            purpose="Verify combined validation, chunk and music-summary planning.",
        ),
        MatrixCase(
            name="validation_music_no_smart_context",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--validate",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
                "--no-smart-context",
            ),
            purpose="Verify validation and music-summary planning with smart context disabled.",
        ),
        MatrixCase(
            name="full_planning_surface",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--build-chunks",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
                "--validate",
                "--use-npu",
                "--npu-workers",
                "4",
                "--gpu-command",
                _planned_gpu_placeholder_command(),
            ),
            purpose="Verify the widest planned CPU/NPU/GPU dry-run surface without executing heavy workloads.",
        ),
        MatrixCase(
            name="full_planning_no_auto_remediation",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--build-chunks",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
                "--validate",
                "--use-npu",
                "--npu-workers",
                "4",
                "--gpu-command",
                _planned_gpu_placeholder_command(),
                "--no-guardrail-auto-remediate",
            ),
            purpose="Verify widest planned dry-run surface with guardrail auto-remediation disabled.",
        ),
        MatrixCase(
            name="full_planning_no_smart_context",
            args=(
                "--dry-run",
                "--write-dry-run-report",
                "--build-chunks",
                "--build-music-summary",
                "--analysis-json",
                str(sample_analysis_json),
                "--validate",
                "--use-npu",
                "--npu-workers",
                "4",
                "--gpu-command",
                _planned_gpu_placeholder_command(),
                "--no-smart-context",
            ),
            purpose="Verify widest planned dry-run surface with smart context disabled.",
        ),
    ]
    if agent_state_packet is not None:
        cases.append(
            MatrixCase(
                name="with_agent_state_packet",
                args=("--dry-run", "--write-dry-run-report", "--agent-state-packet", str(agent_state_packet)),
                purpose="Verify optional agent state packet metadata without changing planned steps.",
            )
        )
    return tuple(cases)


def run_case(repo_root: Path, output_dir: Path, case: MatrixCase) -> dict[str, Any]:
    script = repo_root / "Tools" / "ai" / "run_parallel_artifact_pipeline.py"
    case_output = output_dir / case.name
    case_output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(case_output),
        *case.args,
    ]

    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    duration_sec = round(time.perf_counter() - started, 4)
    report_path = case_output / "ai_pipeline_dry_run_report.json"
    report_payload: dict[str, Any] | None = None
    if report_path.exists():
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            report_payload = {"parse_error": f"{type(exc).__name__}: {exc}"}

    return {
        "name": case.name,
        "purpose": case.purpose,
        "command": command,
        "returncode": completed.returncode,
        "duration_sec": duration_sec,
        "stdout_tail": completed.stdout[-6000:],
        "stderr_tail": completed.stderr[-6000:],
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "report_passed": report_payload.get("passed") if isinstance(report_payload, dict) else None,
        "step_count": report_payload.get("step_count") if isinstance(report_payload, dict) else None,
        "lanes": report_payload.get("lanes") if isinstance(report_payload, dict) else None,
        "summary": report_payload.get("summary") if isinstance(report_payload, dict) else None,
        "schedule": report_payload.get("schedule") if isinstance(report_payload, dict) else None,
        "agent_state_packet": report_payload.get("agent_state_packet") if isinstance(report_payload, dict) else None,
    }


def run_cases(repo_root: Path, output_dir: Path, cases: tuple[MatrixCase, ...], matrix_workers: int, continue_on_error: bool) -> list[dict[str, Any]]:
    """Run matrix cases, preserving deterministic report order."""
    if matrix_workers <= 1:
        results: list[dict[str, Any]] = []
        for case in cases:
            result = run_case(repo_root, output_dir, case)
            results.append(result)
            if result["returncode"] != 0 and not continue_on_error:
                break
        return results

    results_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=matrix_workers) as pool:
        futures = {
            pool.submit(run_case, repo_root, output_dir, case): index
            for index, case in enumerate(cases)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:
                case = cases[index]
                results_by_index[index] = {
                    "name": case.name,
                    "purpose": case.purpose,
                    "command": None,
                    "returncode": 1,
                    "duration_sec": 0.0,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "report_path": None,
                    "report_exists": False,
                    "report_passed": False,
                    "step_count": None,
                    "lanes": None,
                    "summary": None,
                    "schedule": None,
                    "agent_state_packet": None,
                    "matrix_error": f"{type(exc).__name__}: {exc}",
                }
    return [results_by_index[index] for index in sorted(results_by_index)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default="output/ai_pipeline/dry_run_matrix")
    parser.add_argument("--output", default="output/ai_pipeline/dry_run_matrix_report.json")
    parser.add_argument("--markdown-output", default="output/ai_pipeline/dry_run_matrix_report.md")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--matrix-workers",
        type=int,
        default=default_matrix_workers(),
        help="Number of matrix cases to execute concurrently. Default: min(8, CPU count). Use 1 for serial execution.",
    )
    parser.add_argument(
        "--repeat-cases",
        type=int,
        default=1,
        help="Repeat the full case matrix N times with unique output directories for stress testing. Default: 1.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_workers = max(1, args.matrix_workers)
    repeat_count = max(1, args.repeat_cases)
    base_cases = default_cases(repo_root)
    cases = repeat_cases(base_cases, repeat_count)
    results = run_cases(repo_root, output_dir, cases, matrix_workers, args.continue_on_error)

    passed = all(item["returncode"] == 0 and item.get("report_passed") is True for item in results)
    report = {
        "schema_version": 1,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "case_count": len(results),
        "planned_case_count": len(cases),
        "base_case_count": len(base_cases),
        "repeat_cases": repeat_count,
        "matrix_workers": matrix_workers,
        "passed": passed,
        "results": results,
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output = write_dry_run_matrix_markdown(args.markdown_output, report)
    report["markdown_output"] = str(markdown_output)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
