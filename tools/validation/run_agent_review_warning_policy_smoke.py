#!/usr/bin/env python3
"""Smoke-test the integrated agent review warning policy."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/agent_review_warning_policy_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_warning_policy_smoke.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Warning Policy Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Input-nonfatal warning count: `{report.get('input_nonfatal_warning_count')}`")
    lines.append(f"- Fatal report failure count: `{report.get('fatal_report_failure_count')}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def run_smoke(repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    work_dir = repo_root / "output" / "validation" / "agent_review_warning_policy_smoke"
    decision = work_dir / "decision_loop.json"
    gpu = work_dir / "parallel_gpu.json"
    orchestrator = work_dir / "orchestrator.json"
    memory = work_dir / "memory.json"
    policy_output = work_dir / "warning_policy.json"
    policy_markdown = work_dir / "warning_policy.md"

    write_fixture(
        decision,
        {
            "schema_version": 1,
            "kind": "agent_review_decision_loop",
            "repo_root": str(repo_root),
            "passed": True,
            "errors": [],
            "warnings": [],
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "recommendation_count": 2,
            "patch_plan_count": 2,
        },
    )
    write_fixture(
        gpu,
        {
            "schema_version": 1,
            "kind": "agent_gpu_deep_planning_supervised",
            "repo_root": str(repo_root),
            "passed": False,
            "errors": ["json_parse_failure"],
            "warnings": ["model output schema mismatch recovered by deterministic layer"],
            "empty_recommendations_reason": "json_parse_failure",
            "recommendation_count": 0,
        },
    )
    write_fixture(
        orchestrator,
        {
            "schema_version": 1,
            "kind": "agent_gpu_npu_parallel_orchestrator",
            "repo_root": str(repo_root),
            "passed": False,
            "errors": [],
            "warnings": ["provider diagnostic produced zero recommendations"],
            "gpu_empty_recommendations_reason": "evidence_ready_but_no_gpu_plan",
            "gpu_recommended_next_layer": "run_agent_review_decision_loop.py",
        },
    )
    write_fixture(
        memory,
        {
            "schema_version": 1,
            "kind": "agent_runtime_sqlite_memory",
            "repo_root": str(repo_root),
            "passed": True,
            "errors": [],
            "warnings": ["persistent memory opened read-only"],
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    )

    command = [
        sys.executable,
        "Tools/ai/agent_review_warning_policy.py",
        "--repo-root",
        ".",
        "--decision-report",
        str(decision),
        "--report-file",
        str(gpu),
        "--report-file",
        str(orchestrator),
        "--report-file",
        str(memory),
        "--output",
        str(policy_output),
        "--markdown-output",
        str(policy_markdown),
    ]
    returncode, stdout, stderr, runner_error = run_command(command, repo_root, timeout_seconds)
    errors: list[str] = []
    if runner_error:
        errors.append(runner_error)
    if returncode != 0:
        errors.append(f"warning policy returned {returncode}")
    policy, read_error = load_json(policy_output)
    if read_error:
        errors.append(f"unable to read warning policy output: {read_error}")

    if policy:
        if policy.get("passed") is not True:
            errors.append("policy report did not pass")
        if policy.get("input_nonfatal_warning_count") != 2:
            errors.append(f"expected two input_nonfatal warnings, got {policy.get('input_nonfatal_warning_count')!r}")
        if policy.get("fatal_report_failure_count") != 0:
            errors.append(f"expected zero fatal failures, got {policy.get('fatal_report_failure_count')!r}")
        level_counts = policy.get("warning_level_counts", {})
        if level_counts.get("provider", 0) < 2:
            errors.append(f"expected provider warning level count >= 2, got {level_counts.get('provider', 0)!r}")
        if level_counts.get("memory", 0) < 1:
            errors.append(f"expected memory warning level count >= 1, got {level_counts.get('memory', 0)!r}")

    return {
        "schema_version": 1,
        "kind": "agent_review_warning_policy_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "policy_output": rel(policy_output, repo_root),
        "input_nonfatal_warning_count": policy.get("input_nonfatal_warning_count") if policy else None,
        "fatal_report_failure_count": policy.get("fatal_report_failure_count") if policy else None,
        "warning_level_counts": policy.get("warning_level_counts") if policy else {},
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
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_smoke(repo_root, args.timeout_seconds)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    write_text_report(render_markdown(report), markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
