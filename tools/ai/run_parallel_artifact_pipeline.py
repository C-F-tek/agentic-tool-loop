#!/usr/bin/env python3
"""Thin CLI entrypoint for the AI artifact pipeline.

Implementation details live under ``Tools/ai/pipeline/`` so the pipeline can be
validated, refactored and dry-run tested in focused modules.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from pipeline.artifact_contracts import slugify
    from pipeline.cli import build_parser
    from pipeline.preflight import preflight
    from pipeline.remediation import execute_remediation_loop
    from pipeline.scheduler import build_schedule, execute_schedule
    from pipeline.schema_report import build_report, empty_failed_report, write_report_if_requested
    from pipeline.steps import build_parallel_steps, build_serial_steps, build_step_commands
except ImportError:  # Allows package-style imports during external checks.
    from Tools.ai.pipeline.artifact_contracts import slugify  # type: ignore
    from Tools.ai.pipeline.cli import build_parser  # type: ignore
    from Tools.ai.pipeline.preflight import preflight  # type: ignore
    from Tools.ai.pipeline.remediation import execute_remediation_loop  # type: ignore
    from Tools.ai.pipeline.scheduler import build_schedule, execute_schedule  # type: ignore
    from Tools.ai.pipeline.schema_report import build_report, empty_failed_report, write_report_if_requested  # type: ignore
    from Tools.ai.pipeline.steps import build_parallel_steps, build_serial_steps, build_step_commands  # type: ignore


def main() -> int:
    """Run the AI artifact pipeline."""
    args = build_parser().parse_args()

    repo = Path(args.repo_root).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    pf = preflight(repo, out, args)
    if not pf["passed"] and not args.continue_on_error:
        report = empty_failed_report(repo, out, args.dry_run, pf)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    commands = build_step_commands(repo, out, args)
    track_slug = slugify(args.track_stem)
    schedule = build_schedule(
        build_serial_steps(commands, track_slug),
        build_parallel_steps(commands, out, args),
    )

    results = execute_schedule(
        schedule,
        repo=repo,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
    )
    remediation_loop = execute_remediation_loop(repo, out, args, results)
    report = build_report(repo, out, args, pf, results, remediation_loop, schedule=schedule.to_dict())
    write_report_if_requested(out, args, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
