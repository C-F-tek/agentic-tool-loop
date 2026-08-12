#!/usr/bin/env python3
"""Smoke-test the report-only runtime tool broker without providers."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_broker(repo_root: Path, request_file: Path, output: Path, markdown: Path, stamp: str, dry_run: bool) -> tuple[int, str, str]:
    command = [
        sys.executable,
        "Tools/ai/agent_runtime_tool_broker.py",
        "--repo-root",
        ".",
        "--request-file",
        str(request_file),
        "--tool-output-dir",
        f"output/ai_runtime_tools/broker_smoke_{stamp}",
        "--stamp",
        stamp,
        "--timeout-seconds",
        "240",
        "--output",
        str(output),
        "--markdown-output",
        str(markdown),
    ]
    if dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:]


def build_smoke_request() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agent_runtime_tool_broker_smoke_request",
        "tool_requests": [
            {
                "id": "tools_inventory",
                "tool": "build_agent_agnostic_tool_inventory",
                "reason": "Planner needs to discover reusable tools before proposing refactor work.",
                "args": {"root": ["Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu"]},
            },
            {
                "id": "line_count",
                "tool": "build_python_line_count_csv",
                "reason": "Planner needs complete Python file line-count inventory.",
                "args": {},
            },
            {
                "id": "transient_context",
                "tool": "build_agent_transient_request_context",
                "reason": "Planner needs request-scoped context artifact.",
                "args": {"memory_note": "Runtime broker smoke: report-only context aggregation."},
            },
            {
                "id": "operational_memory_status",
                "tool": "runtime_sqlite_memory",
                "reason": "Doctor tool needs scratch operational memory status.",
                "args": {"action": "status", "scope": "operational"},
            },
            {
                "id": "operational_memory_remember",
                "tool": "runtime_sqlite_memory",
                "reason": "Doctor tool stores transient working context in clearable scratch memory.",
                "args": {
                    "action": "remember",
                    "scope": "operational",
                    "summary": "runtime broker smoke operational memory",
                    "content": "This is a temporary operational memory record created by smoke validation.",
                    "tag": ["smoke", "operational_memory"]
                },
            },
            {
                "id": "operational_memory_search",
                "tool": "runtime_sqlite_memory",
                "reason": "Doctor tool retrieves transient working context.",
                "args": {"action": "search", "scope": "operational", "query": "temporary operational", "limit": 5},
            },
            {
                "id": "persistent_memory_status",
                "tool": "runtime_sqlite_memory",
                "reason": "Doctor tool inspects persistent memory only in read-only mode.",
                "args": {"action": "status", "scope": "persistent"},
            },
            {
                "id": "blocked_free_shell",
                "tool": "shell",
                "reason": "This must be blocked because free shell is not allowlisted.",
                "args": {"command": "whoami"},
            },
        ],
    }


def validate_report(report: dict[str, Any], *, dry_run: bool) -> list[str]:
    errors: list[str] = []
    if report.get("kind") != "agent_runtime_tool_broker":
        errors.append("unexpected report kind")
    if report.get("tool_request_count") != 8:
        errors.append("expected 8 tool requests")
    if report.get("blocked_tool_count") != 1:
        errors.append("expected one blocked non-allowlisted tool")
    if dry_run:
        if report.get("tool_execution_count") != 0:
            errors.append("dry-run should not execute tools")
    else:
        if report.get("tool_execution_count") != 7:
            errors.append("expected seven executed allowlisted tools")
    for key in (
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "blender_runtime_execution_performed",
        "git_write_performed",
    ):
        if report.get(key) is not False:
            errors.append(f"{key} must be false")
    if report.get("guardrails", {}).get("free_shell_exposed") is not False:
        errors.append("free_shell_exposed guardrail must be false")
    if report.get("guardrails", {}).get("allowlist_enforced") is not True:
        errors.append("allowlist_enforced guardrail must be true")
    if report.get("operational_sqlite_write_performed") is not True:
        errors.append("operational_sqlite_write_performed should be true after operational remember")
    if report.get("sqlite_write_performed") is not False:
        errors.append("protected sqlite_write_performed must remain false")
    if report.get("persistent_memory_write_performed") is not False:
        errors.append("persistent_memory_write_performed must remain false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    stamp = now_stamp()
    request_file = resolve_path(repo_root, f"output/validation/agent_runtime_tool_broker_smoke_request_{stamp}.json")
    broker_output = resolve_path(repo_root, f"output/validation/agent_runtime_tool_broker_smoke_{stamp}.json")
    broker_markdown = resolve_path(repo_root, f"output/validation/agent_runtime_tool_broker_smoke_{stamp}.md")
    final_output = resolve_path(repo_root, args.output or f"output/validation/agent_runtime_tool_broker_smoke_result_{stamp}.json")
    final_markdown = resolve_path(repo_root, args.markdown_output or f"output/validation/agent_runtime_tool_broker_smoke_result_{stamp}.md")

    write_json(request_file, build_smoke_request())
    returncode, stdout, stderr = run_broker(repo_root, request_file, broker_output, broker_markdown, stamp, args.dry_run)
    broker_report = read_json(broker_output) if broker_output.exists() else {}
    errors = validate_report(broker_report, dry_run=args.dry_run)
    if returncode not in {0, 2}:
        errors.append(f"broker returned unexpected code {returncode}")
    if returncode == 2 and not broker_report.get("blocked_tool_count"):
        errors.append("broker failed without expected blocked tool")

    report = {
        "schema_version": 1,
        "kind": "agent_runtime_tool_broker_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "dry_run": bool(args.dry_run),
        "request_file": str(request_file),
        "broker_output": str(broker_output),
        "broker_markdown": str(broker_markdown),
        "broker_returncode": returncode,
        "broker_stdout_tail": stdout,
        "broker_stderr_tail": stderr,
        "broker_summary": {
            "tool_request_count": broker_report.get("tool_request_count"),
            "tool_execution_count": broker_report.get("tool_execution_count"),
            "blocked_tool_count": broker_report.get("blocked_tool_count"),
            "failed_tool_count": broker_report.get("failed_tool_count"),
        },
    }
    write_json(final_output, report)
    final_markdown.parent.mkdir(parents=True, exist_ok=True)
    final_markdown.write_text(
        "\n".join(
            [
                "# Agent Runtime Tool Broker Smoke",
                "",
                f"- Passed: `{report['passed']}`",
                f"- Dry run: `{report['dry_run']}`",
                f"- Tool requests: `{report['broker_summary']['tool_request_count']}`",
                f"- Tool executions: `{report['broker_summary']['tool_execution_count']}`",
                f"- Blocked tools: `{report['broker_summary']['blocked_tool_count']}`",
                f"- Provider execution performed: `{report['provider_execution_performed']}`",
                f"- Patch application performed: `{report['patch_application_performed']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({
        "passed": report["passed"],
        "output": str(final_output),
        "markdown": str(final_markdown),
        **report["broker_summary"],
        "provider_execution_performed": False,
        "patch_application_performed": False,
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

