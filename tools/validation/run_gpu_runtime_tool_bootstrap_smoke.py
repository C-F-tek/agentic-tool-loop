#!/usr/bin/env python3
"""Smoke test deterministic runtime tool bootstrap before GPU planning.

This smoke intentionally runs the supervised GPU planner without provider
execution. The supervised runner is expected to report passed=false in this
mode because --use-ollama is absent, but the deterministic runtime tool
bootstrap must still execute and pass when runtime broker support is enabled.

The smoke therefore validates the bootstrap metrics and guardrails directly
instead of requiring the full provider-backed supervised run to pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], ""
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 - smoke report must capture failures.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GPU Runtime Tool Bootstrap Smoke",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Patch application performed: `{report.get('patch_application_performed')}`",
        f"- Runtime tool bootstrap executed: `{report.get('runtime_tool_bootstrap_executed')}`",
        f"- Runtime tool bootstrap passed: `{report.get('runtime_tool_bootstrap_passed')}`",
        f"- Runtime tool bootstrap request count: `{report.get('runtime_tool_bootstrap_request_count')}`",
        f"- Runtime tool bootstrap execution count: `{report.get('runtime_tool_bootstrap_execution_count')}`",
        f"- Runtime tool bootstrap failed count: `{report.get('runtime_tool_bootstrap_failed_count')}`",
        f"- Runtime tool bootstrap blocked count: `{report.get('runtime_tool_bootstrap_blocked_count')}`",
        f"- Persistent memory write performed: `{report.get('persistent_memory_write_performed')}`",
        "",
        "## Errors",
        "",
    ]
    if report.get("errors"):
        lines.extend(f"- {item}" for item in report.get("errors", []))
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if report.get("warnings"):
        lines.extend(f"- {item}" for item in report.get("warnings", []))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/gpu_runtime_tool_bootstrap_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/gpu_runtime_tool_bootstrap_smoke.md")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    supervised_output = output.with_name(output.stem + "_supervised_no_provider.json")
    supervised_markdown = output.with_name(output.stem + "_supervised_no_provider.md")

    command = [
        sys.executable,
        "Tools/ai/run_agent_gpu_deep_planning_supervised.py",
        "--repo-root",
        ".",
        "--enable-runtime-tool-broker",
        "--output",
        str(supervised_output),
        "--markdown-output",
        str(supervised_markdown),
    ]

    help_text = subprocess.run(
        [sys.executable, "Tools/ai/run_agent_gpu_deep_planning_supervised.py", "--help"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    ).stdout
    if "--enable-runtime-tool-bootstrap" in help_text:
        command.insert(command.index("--output"), "--enable-runtime-tool-bootstrap")

    returncode, stdout, stderr, command_error = run_command(command, repo_root, args.timeout_seconds)

    errors: list[str] = []
    warnings: list[str] = []
    supervised_report: dict[str, Any] = {}
    if command_error:
        errors.append(command_error)
    if not supervised_output.exists():
        errors.append(f"missing supervised output: {repo_rel(supervised_output, repo_root)}")
    else:
        try:
            supervised_report = read_json(supervised_output)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"failed to parse supervised output: {type(exc).__name__}: {exc}")

    # In no-provider mode the supervised runner may return rc=2 / passed=false
    # because --use-ollama is intentionally absent. That is not a smoke failure
    # if the deterministic bootstrap itself executed and passed.
    if returncode not in (0, 2):
        errors.append(f"unexpected supervised returncode: {returncode}")

    runtime_tool_bootstrap_executed = supervised_report.get("runtime_tool_bootstrap_executed")
    runtime_tool_bootstrap_passed = supervised_report.get("runtime_tool_bootstrap_passed")
    runtime_tool_bootstrap_request_count = supervised_report.get("runtime_tool_bootstrap_request_count")
    runtime_tool_bootstrap_execution_count = supervised_report.get("runtime_tool_bootstrap_execution_count")
    runtime_tool_bootstrap_failed_count = supervised_report.get("runtime_tool_bootstrap_failed_count")
    runtime_tool_bootstrap_blocked_count = supervised_report.get("runtime_tool_bootstrap_blocked_count")

    expected = {
        "runtime_tool_bootstrap_executed": True,
        "runtime_tool_bootstrap_passed": True,
        "runtime_tool_bootstrap_request_count": 7,
        "runtime_tool_bootstrap_execution_count": 7,
        "runtime_tool_bootstrap_failed_count": 0,
        "runtime_tool_bootstrap_blocked_count": 0,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "persistent_memory_write_performed": False,
    }
    observed = {
        "runtime_tool_bootstrap_executed": runtime_tool_bootstrap_executed,
        "runtime_tool_bootstrap_passed": runtime_tool_bootstrap_passed,
        "runtime_tool_bootstrap_request_count": runtime_tool_bootstrap_request_count,
        "runtime_tool_bootstrap_execution_count": runtime_tool_bootstrap_execution_count,
        "runtime_tool_bootstrap_failed_count": runtime_tool_bootstrap_failed_count,
        "runtime_tool_bootstrap_blocked_count": runtime_tool_bootstrap_blocked_count,
        "provider_execution_performed": supervised_report.get("provider_execution_performed"),
        "patch_application_performed": supervised_report.get("patch_application_performed"),
        "persistent_memory_write_performed": supervised_report.get("persistent_memory_write_performed", False),
    }
    for key, expected_value in expected.items():
        if observed.get(key) != expected_value:
            errors.append(f"{key}: expected {expected_value!r}, got {observed.get(key)!r}")

    report = {
        "schema_version": 1,
        "kind": "gpu_runtime_tool_bootstrap_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": bool(supervised_report.get("provider_execution_performed", False)),
        "patch_application_performed": bool(supervised_report.get("patch_application_performed", False)),
        "source_writes_performed": False,
        "sqlite_write_performed": bool(supervised_report.get("sqlite_write_performed", False)),
        "persistent_memory_write_performed": bool(supervised_report.get("persistent_memory_write_performed", False)),
        "runtime_tool_bootstrap_executed": runtime_tool_bootstrap_executed,
        "runtime_tool_bootstrap_passed": runtime_tool_bootstrap_passed,
        "runtime_tool_bootstrap_request_count": runtime_tool_bootstrap_request_count,
        "runtime_tool_bootstrap_execution_count": runtime_tool_bootstrap_execution_count,
        "runtime_tool_bootstrap_failed_count": runtime_tool_bootstrap_failed_count,
        "runtime_tool_bootstrap_blocked_count": runtime_tool_bootstrap_blocked_count,
        "supervised_returncode": returncode,
        "supervised_output": repo_rel(supervised_output, repo_root),
        "supervised_markdown": repo_rel(supervised_markdown, repo_root),
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "guardrails": {
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "persistent_memory_write_performed": False,
            "runtime_tool_bootstrap_report_only": True,
            "manual_review_required": True,
        },
    }
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(build_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "runtime_tool_bootstrap_executed": report["runtime_tool_bootstrap_executed"],
                "runtime_tool_bootstrap_passed": report["runtime_tool_bootstrap_passed"],
                "runtime_tool_bootstrap_request_count": report["runtime_tool_bootstrap_request_count"],
                "runtime_tool_bootstrap_execution_count": report["runtime_tool_bootstrap_execution_count"],
                "runtime_tool_bootstrap_failed_count": report["runtime_tool_bootstrap_failed_count"],
                "runtime_tool_bootstrap_blocked_count": report["runtime_tool_bootstrap_blocked_count"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
