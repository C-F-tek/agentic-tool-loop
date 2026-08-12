"""Reusable command runners for AI artifact pipeline steps."""
from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from .models import PipelineResult, PipelineStep


def run_step(
    step: PipelineStep,
    *,
    cwd: str | Path,
    dry_run: bool = False,
    stdout_limit: int = 8000,
    stderr_limit: int = 8000,
) -> PipelineResult:
    """Run or preview a single pipeline step."""
    start = time.perf_counter()
    if dry_run:
        return PipelineResult(
            step=step,
            returncode=0,
            duration_sec=0.0,
            stdout="",
            stderr="",
            dry_run=True,
            planned_only=True,
        )

    try:
        done = subprocess.run(
            list(step.command),
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return PipelineResult(
            step=step,
            returncode=done.returncode,
            duration_sec=round(time.perf_counter() - start, 4),
            stdout=done.stdout[-stdout_limit:],
            stderr=done.stderr[-stderr_limit:],
            dry_run=False,
            planned_only=False,
        )
    except Exception as exc:
        return PipelineResult(
            step=step,
            returncode=1,
            duration_sec=round(time.perf_counter() - start, 4),
            stdout="",
            stderr="",
            dry_run=False,
            planned_only=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_serial(
    steps: Iterable[PipelineStep],
    *,
    cwd: str | Path,
    dry_run: bool = False,
    continue_on_error: bool = False,
) -> list[PipelineResult]:
    """Run steps sequentially."""
    results: list[PipelineResult] = []
    for step in steps:
        result = run_step(step, cwd=cwd, dry_run=dry_run)
        results.append(result)
        if not result.ok and not continue_on_error:
            break
    return results


def run_parallel(
    steps: Iterable[PipelineStep],
    *,
    cwd: str | Path,
    dry_run: bool = False,
    max_workers: int | None = None,
) -> list[PipelineResult]:
    """Run steps concurrently and return results as they complete."""
    pending = list(steps)
    if not pending:
        return []

    workers = max_workers or len(pending)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_step, step, cwd=cwd, dry_run=dry_run): step for step in pending}
        return [future.result() for future in as_completed(futures)]


def all_results_ok(results: Iterable[PipelineResult]) -> bool:
    """Return True if all results are successful or explicitly allowed to fail."""
    return all(result.ok for result in results)
