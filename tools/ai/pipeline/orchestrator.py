"""Runtime orchestration helpers for AI artifact pipeline steps."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .compat import run_pipeline_step
from .models import PipelineStep


def run_serial_steps(steps: list[PipelineStep], repo: Path, dry_run: bool, continue_on_error: bool) -> list[dict]:
    """Run ordered pipeline steps and stop on failure unless configured otherwise."""
    results: list[dict] = []
    for step in steps:
        result = run_pipeline_step(step, repo, dry_run)
        results.append(result)
        if result["returncode"] and not continue_on_error:
            break
    return results


def run_parallel_steps(steps: list[PipelineStep], repo: Path, dry_run: bool) -> list[dict]:
    """Run independent pipeline steps concurrently."""
    if not steps:
        return []
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(steps)) as pool:
        futures = {pool.submit(run_pipeline_step, step, repo, dry_run): step for step in steps}
        for future in as_completed(futures):
            results.append(future.result())
    return results
