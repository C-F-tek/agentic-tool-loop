#!/usr/bin/env python3
"""Smoke-test schema-repair retry bootstrap safety.

This validator checks that schema-repair retry aggregate counters are not
referenced inside run_runtime_tool_broker_for_round(), where they would be
undefined during runtime-tool bootstrap.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Schema Repair Retry Bootstrap Smoke", ""]
    for key in (
        "passed",
        "case_count",
        "failed_case_count",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
    ):
        lines.append(f"- `{key}`: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def extract_function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"function not found: {function_name}")

    next_start = source.find("\ndef ", start + len(marker))
    if next_start < 0:
        return source[start:]
    return source[start:next_start]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--output",
        default="output/validation/schema_repair_retry_bootstrap_smoke.json",
    )
    parser.add_argument(
        "--markdown-output",
        default="output/validation/schema_repair_retry_bootstrap_smoke.md",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    target = repo_root / "Tools" / "ai" / "run_agent_gpu_deep_planning_supervised.py"

    errors: list[str] = []
    warnings: list[str] = []

    try:
        source = target.read_text(encoding="utf-8")
    except OSError as exc:
        source = ""
        errors.append(f"could not read target: {type(exc).__name__}: {exc}")

    broker_body = ""
    if source:
        try:
            broker_body = extract_function_body(source, "run_runtime_tool_broker_for_round")
        except ValueError as exc:
            errors.append(str(exc))

    forbidden_in_broker = (
        "schema_repair_retry_attempt_count",
        "schema_repair_retry_accept_count",
    )
    for token in forbidden_in_broker:
        if token in broker_body:
            errors.append(f"forbidden aggregate retry counter leaked into broker bootstrap function: {token}")

    if source and "def run_schema_repair_retry_for_round(" not in source:
        errors.append("schema repair retry helper missing from supervised runner")

    if source and "schema_repair_retry_attempt_count = sum(" not in source:
        errors.append("aggregate retry attempt counter missing from build_report/report aggregation")

    if source and "schema_repair_retry_accept_count = sum(" not in source:
        errors.append("aggregate retry accept counter missing from build_report/report aggregation")

    if source and '"schema_repair_retry_attempt_count": schema_repair_retry_attempt_count' not in source:
        errors.append("top-level schema_repair_retry_attempt_count report field missing")

    if source and '"schema_repair_retry_accept_count": schema_repair_retry_accept_count' not in source:
        errors.append("top-level schema_repair_retry_accept_count report field missing")

    report = {
        "schema_version": 1,
        "kind": "schema_repair_retry_bootstrap_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "target": str(target),
        "passed": not errors,
        "case_count": 1,
        "failed_case_count": 1 if errors else 0,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_touched": False,
        "git_write_performed": False,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }

    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root / output

    markdown = Path(args.markdown_output)
    if not markdown.is_absolute():
        markdown = repo_root / markdown

    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
