"""Pipeline step builders for AI artifact orchestration."""
from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from .artifact_contracts import (
    EXPECTED_CHUNK_ARTIFACTS,
    EXPECTED_MUSIC_ARTIFACTS,
    EXPECTED_SMART_CONTEXT_ARTIFACTS,
    EXPECTED_WAVE_REVIEW_ARTIFACTS,
    slugify,
)
from .compat import pipeline_step
from .models import PipelineStep


def build_step_commands(repo: Path, out: Path, args: Any) -> dict[str, list[str]]:
    """Build command argv lists for enabled artifact pipeline stages."""
    py = sys.executable
    track_slug = slugify(args.track_stem)

    def script(path: str) -> str:
        return str((repo / path).resolve())

    commands: dict[str, list[str]] = {}
    if args.review_wave_entrypoints:
        commands["review_wave_entrypoints"] = [
            py,
            script("Tools/ai/review_wave_entrypoints.py"),
            "--repo-root",
            str(repo),
            "--output",
            str(out / "wave_entrypoint_review.json"),
        ]
    if args.build_chunks:
        commands["build_semantic_code_chunks"] = [py, script("Tools/npu/build_semantic_code_chunks.py"), "--repo-root", str(repo)]
    if args.build_music_summary:
        commands["build_music_intermediates"] = [
            py,
            script("Tools/ai/build_music_intermediates.py"),
            "--analysis-json",
            str(Path(args.analysis_json).resolve()),
            "--output-dir",
            str(out),
        ]
    if args.smart_context:
        commands["build_smart_ai_context"] = [
            py,
            script("Tools/workflow/smart_ai_context.py"),
            "--repo-root",
            str(repo),
            "--track-stem",
            args.track_stem,
            "--task",
            args.smart_task,
            "--output-dir",
            str(out / "smart_context"),
            "--max-packet-chars",
            str(args.smart_max_packet_chars),
            "--max-capsule-chars",
            str(args.smart_max_capsule_chars),
        ]
    if args.use_npu:
        commands["npu_artifact_review"] = [
            py,
            script("Tools/npu/run_npu_artifact_reviewer.py"),
            "--input",
            str(out),
            "--output",
            str(out / "npu_artifact_review.json"),
            "--max-workers",
            str(args.npu_workers),
        ]
    if args.npu_guardrail:
        guardrail_input = out / "smart_context" / f"{track_slug}_smart_context_packet.json" if args.smart_context else out
        commands["npu_guardrail"] = [
            py,
            script("Tools/npu/npu_guardrail_service.py"),
            "--input",
            str(guardrail_input),
            "--output",
            str(out / "npu_guardrail_report.json"),
        ]
    if args.validate:
        commands["validate_ai_artifacts"] = [
            py,
            script("Tools/ai/validate_ai_artifacts.py"),
            "--repo-root",
            str(repo),
            "--artifact-dir",
            str(out),
            "--output",
            str(out / "ai_validation_report.json"),
            "--allow-errors",
        ]
    return commands


def build_serial_steps(commands: dict[str, list[str]], track_slug: str) -> list[PipelineStep]:
    """Build ordered CPU-side pipeline steps."""
    serial: list[PipelineStep] = []
    if "review_wave_entrypoints" in commands:
        serial.append(
            pipeline_step(
                "review_wave_entrypoints",
                "CPU",
                "Review first-wave WAV artifact scripts and emit future guardrail flags.",
                EXPECTED_WAVE_REVIEW_ARTIFACTS,
                commands["review_wave_entrypoints"],
            )
        )
    if "build_semantic_code_chunks" in commands:
        serial.append(
            pipeline_step(
                "build_semantic_code_chunks",
                "CPU",
                "Build symbol-aware repository context for AI retrieval.",
                EXPECTED_CHUNK_ARTIFACTS,
                commands["build_semantic_code_chunks"],
            )
        )
    if "build_music_intermediates" in commands:
        serial.append(
            pipeline_step(
                "build_music_intermediates",
                "CPU",
                "Build compact AI-friendly music artifacts from the full analysis JSON.",
                EXPECTED_MUSIC_ARTIFACTS,
                commands["build_music_intermediates"],
            )
        )
    if "build_smart_ai_context" in commands:
        serial.append(
            pipeline_step(
                "build_smart_ai_context",
                "CPU",
                "Build hierarchical capsules and ranked smart context packet for central AI.",
                [item.format(track_slug=track_slug) for item in EXPECTED_SMART_CONTEXT_ARTIFACTS],
                commands["build_smart_ai_context"],
            )
        )
    if "validate_ai_artifacts" in commands:
        serial.append(
            pipeline_step(
                "validate_ai_artifacts",
                "CPU",
                "Validate generated artifacts and apply task-capsule guardrails.",
                ["ai_validation_report.json"],
                commands["validate_ai_artifacts"],
            )
        )
    return serial


def build_parallel_steps(commands: dict[str, list[str]], out: Path, args: Any) -> list[PipelineStep]:
    """Build concurrent NPU/GPU pipeline steps."""
    parallel: list[PipelineStep] = []
    if "npu_artifact_review" in commands:
        parallel.append(
            pipeline_step(
                "npu_artifact_review",
                "NPU",
                "Review compact artifacts for schema, size, blocked patterns, and obvious risks.",
                [str(out / "npu_artifact_review.json")],
                commands["npu_artifact_review"],
            )
        )
    if "npu_guardrail" in commands:
        parallel.append(
            pipeline_step(
                "npu_guardrail",
                "NPU",
                "Always-on guardrail/preflight plus action queue for corrections and enrichment.",
                [str(out / "npu_guardrail_report.json"), str(out / "npu_guardrail_action_queue.json")],
                commands["npu_guardrail"],
            )
        )
    if args.gpu_command:
        gpu_command = shlex.split(
            args.gpu_command.format(
                brief=str(out / "ai_scene_brief.json"),
                output=str(out / "gpu_planner_output.json"),
            )
        )
        parallel.append(
            pipeline_step(
                "gpu_command",
                "GPU",
                "Run optional heavy planner/generator command.",
                [str(out / "gpu_planner_output.json")],
                gpu_command,
            )
        )
    return parallel
