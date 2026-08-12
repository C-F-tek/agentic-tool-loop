#!/usr/bin/env python3
"""Smoke-test the repository consistency mapper."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/repository_consistency_map_smoke.json"
DEFAULT_MARKDOWN = "output/validation/repository_consistency_map_smoke.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return {}, "JSON root is not an object"
    return data, None


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], None
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def validate_mapper_report(mapper_report: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if mapper_report.get("kind") != "repository_consistency_map":
        errors.append(f"unexpected mapper kind: {mapper_report.get('kind')}")
    if mapper_report.get("passed") is not True:
        errors.append("mapper report did not pass")
    scope = mapper_report.get("scope") if isinstance(mapper_report.get("scope"), dict) else {}
    if int(scope.get("markdown_file_count") or 0) <= 0:
        errors.append("expected markdown_file_count > 0")
    if int(scope.get("python_file_count") or 0) <= 0:
        errors.append("expected python_file_count > 0")
    if mapper_report.get("provider_execution_performed") is not False:
        errors.append("mapper must not execute providers")
    if mapper_report.get("patch_application_performed") is not False:
        errors.append("mapper must not apply patches")
    if mapper_report.get("sqlite_write_performed") is not False:
        errors.append("mapper must not write SQLite")
    warnings.extend(str(item) for item in mapper_report.get("warnings", [])[:20])
    return errors, warnings


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Repository Consistency Map Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Mapper report reused: `{report.get('mapper_report_reused')}`")
    lines.append(f"- Workers requested: `{report.get('workers_requested')}`")
    lines.append(f"- Elapsed seconds: `{report.get('elapsed_seconds')}`")
    lines.append(f"- Finding count: `{report.get('finding_count')}`")
    lines.append(f"- Markdown reference count: `{report.get('markdown_reference_count')}`")
    lines.append(f"- Markdown Python command count: `{report.get('markdown_python_command_count')}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- SQLite write performed: `{report['sqlite_write_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def run_smoke(repo_root: Path, timeout_seconds: int, workers: int, map_report: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[str] = []
    warnings: list[str] = []
    stdout = ""
    stderr = ""
    returncode = 0
    runner_error: str | None = None
    mapper_report_reused = bool(map_report)

    if map_report:
        map_output = Path(map_report)
        if not map_output.is_absolute():
            map_output = repo_root / map_output
        map_markdown: Path | None = None
    else:
        map_output = repo_root / "output" / "validation" / "repository_consistency_map_smoke_map.json"
        map_markdown = repo_root / "output" / "validation" / "repository_consistency_map_smoke_map.md"
        command = [
            sys.executable,
            "Tools/ai/build_repository_consistency_map.py",
            "--repo-root",
            ".",
            "--output",
            str(map_output),
            "--markdown-output",
            str(map_markdown),
            "--max-detail-items",
            "500",
            "--workers",
            str(workers),
        ]
        returncode, stdout, stderr, runner_error = run_command(command, repo_root, timeout_seconds)
        if runner_error:
            errors.append(runner_error)
        if returncode != 0:
            errors.append(f"mapper returned {returncode}")

    mapper_report, read_error = load_json(map_output)
    if read_error:
        errors.append(f"unable to read mapper output: {read_error}")
    if mapper_report:
        validation_errors, validation_warnings = validate_mapper_report(mapper_report)
        errors.extend(validation_errors)
        warnings.extend(validation_warnings)

    scope = mapper_report.get("scope", {}) if mapper_report else {}
    elapsed_seconds = round(time.perf_counter() - started, 3)
    return {
        "schema_version": 1,
        "kind": "repository_consistency_map_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "returncode": returncode,
        "workers_requested": workers,
        "mapper_report_reused": mapper_report_reused,
        "elapsed_seconds": elapsed_seconds,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "runner_error": runner_error,
        "mapper_output": rel(map_output, repo_root),
        "mapper_markdown": rel(map_markdown, repo_root) if map_markdown else None,
        "finding_count": mapper_report.get("finding_count") if mapper_report else None,
        "severity_counts": mapper_report.get("severity_counts") if mapper_report else {},
        "markdown_reference_count": scope.get("markdown_reference_count"),
        "markdown_python_command_count": scope.get("markdown_python_command_count"),
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--workers", type=int, default=8, help="Worker count passed to build_repository_consistency_map.py when not reusing --map-report.")
    parser.add_argument("--map-report", help="Existing repository_consistency_map JSON to validate instead of rerunning the mapper.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_smoke(repo_root, args.timeout_seconds, args.workers, args.map_report)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    write_text_report(render_markdown(report), markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
