"""Lane-aware scheduler policy for the AI artifact pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import PipelineStep
from .orchestrator import run_parallel_steps, run_serial_steps


@dataclass(frozen=True)
class PipelineSchedule:
    """A concrete execution schedule for artifact pipeline steps."""

    serial: tuple[PipelineStep, ...]
    parallel: tuple[PipelineStep, ...]

    @property
    def serial_count(self) -> int:
        return len(self.serial)

    @property
    def parallel_count(self) -> int:
        return len(self.parallel)

    @property
    def total_count(self) -> int:
        return self.serial_count + self.parallel_count

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-serializable schedule summary."""
        return {
            "serial_count": self.serial_count,
            "parallel_count": self.parallel_count,
            "total_count": self.total_count,
            "serial": [step.name for step in self.serial],
            "parallel": [step.name for step in self.parallel],
            "parallel_lanes": sorted({step.lane.value for step in self.parallel}),
        }


def build_schedule(serial: list[PipelineStep], parallel: list[PipelineStep]) -> PipelineSchedule:
    """Build an immutable schedule from step lists."""
    return PipelineSchedule(serial=tuple(serial), parallel=tuple(parallel))


def should_run_parallel(results: list[dict], schedule: PipelineSchedule) -> bool:
    """Return True when parallel steps should run after serial steps."""
    if not schedule.parallel:
        return False
    return all(item.get("returncode") == 0 for item in results)


def execute_schedule(
    schedule: PipelineSchedule,
    *,
    repo: Path,
    dry_run: bool,
    continue_on_error: bool,
) -> list[dict]:
    """Execute serial steps first and parallel lane steps only if safe."""
    results = run_serial_steps(list(schedule.serial), repo, dry_run, continue_on_error)
    if should_run_parallel(results, schedule):
        results.extend(run_parallel_steps(list(schedule.parallel), repo, dry_run))
    return results
