"""Compatibility adapters between legacy pipeline reports and reusable models."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import PipelineLane, PipelineResult, PipelineStep
from .runner import run_step


def legacy_result_payload(result: PipelineResult) -> dict[str, Any]:
    """Return the legacy command-result shape used by schema v6 reports."""
    payload: dict[str, Any] = {
        "command": list(result.step.command),
        "dry_run": result.dry_run,
        "returncode": result.returncode,
        "duration_sec": result.duration_sec,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "planned_only": result.planned_only,
    }
    if result.error:
        payload["error"] = result.error
    return payload


def step_result_payload(result: PipelineResult) -> dict[str, Any]:
    """Return the report-compatible payload for a named pipeline step."""
    payload = legacy_result_payload(result)
    payload.update(
        {
            "name": result.step.name,
            "lane": result.step.lane.value,
            "purpose": result.step.purpose,
            "expected_outputs": list(result.step.expected_outputs),
            "pass_index": result.step.pass_index,
        }
    )
    return payload


def pipeline_step(
    name: str,
    lane: str | PipelineLane,
    purpose: str,
    expected_outputs: list[str] | tuple[str, ...],
    command: list[str] | tuple[str, ...],
    pass_index: int = 0,
) -> PipelineStep:
    """Build a reusable pipeline step while preserving the legacy call shape."""
    return PipelineStep.from_command(
        name=name,
        lane=lane,
        purpose=purpose,
        expected_outputs=expected_outputs,
        command=command,
        pass_index=pass_index,
    )


def run_pipeline_step(step: PipelineStep, cwd: Path, dry: bool) -> dict[str, Any]:
    """Execute a PipelineStep and return the existing schema-v6 step payload."""
    return step_result_payload(run_step(step, cwd=cwd, dry_run=dry))


def run_legacy_command(cmd: list[str], cwd: Path, dry: bool) -> dict[str, Any]:
    """Run a raw command through the reusable runner and keep legacy output."""
    step = PipelineStep.from_command(
        name="legacy_command",
        command=cmd,
        lane=PipelineLane.CPU,
    )
    return legacy_result_payload(run_step(step, cwd=cwd, dry_run=dry))
