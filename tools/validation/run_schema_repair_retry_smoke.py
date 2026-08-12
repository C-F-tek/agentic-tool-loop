#!/usr/bin/env python3
"""Smoke-test schema repair retry prompt and acceptance policy."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.schema_repair_context import (
        build_schema_repair_retry_prompt,
        should_attempt_schema_repair_retry,
    )
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.schema_repair_context import (  # type: ignore
        build_schema_repair_retry_prompt,
        should_attempt_schema_repair_retry,
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Schema Repair Retry Smoke", ""]
    for key in (
        "passed",
        "case_count",
        "failed_case_count",
        "retry_required",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/schema_repair_retry_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/schema_repair_retry_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    bad_parsed = {"response": {"message": "Here is a summary instead of planner JSON."}}
    diagnostics = {
        "json_ok": True,
        "schema_ok": False,
        "schema_errors": ["missing top-level keys: recommendations, tool_requests"],
        "context_echo_detected": False,
        "model_output_schema_mismatch": True,
        "empty_recommendations_reason": "model_output_schema_mismatch",
    }
    context_reports = [
        {
            "kind": "runtime_tool_feedback_context",
            "source": "provider_tool_requests",
            "round": 1,
            "passed": True,
            "summary": {"tool_execution_count": 4, "failed_tool_count": 0, "blocked_tool_count": 0},
            "tool_results": [
                {
                    "id": "syntax",
                    "tool": "check_python_syntax",
                    "executed": True,
                    "blocked": False,
                    "returncode": 0,
                    "summary": {"passed": True, "checked_count": 300, "failed_count": 0},
                }
            ],
        }
    ]
    retry_required = should_attempt_schema_repair_retry(
        parsed_response=bad_parsed,
        parse_diagnostics=diagnostics,
        evidence_ready_for_manual_patch_count=12,
        valid_tool_request_count=0,
    )
    prompt = build_schema_repair_retry_prompt(
        provider="gpu_ollama",
        round_index=2,
        objective="Produce schema-valid recommendations",
        raw_response=json.dumps(bad_parsed),
        parsed_response=bad_parsed,
        parse_diagnostics=diagnostics,
        context_reports=context_reports,
        rounds=[],
        evidence_ready_for_manual_patch_count=12,
    )

    errors: list[str] = []
    if not retry_required:
        errors.append("schema repair retry was not required for schema mismatch")
    for needle in (
        "Return JSON only",
        "required_top_level_keys",
        "recommendation_template",
        "runtime_tool_evidence",
        "bad_response",
    ):
        if needle not in prompt:
            errors.append(f"repair prompt missing {needle!r}")
    if "patch_application" in prompt and "Do not request shell" not in prompt:
        errors.append("guardrail language appears incomplete")

    report = {
        "schema_version": 1,
        "kind": "schema_repair_retry_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "case_count": 1,
        "failed_case_count": 1 if errors else 0,
        "retry_required": retry_required,
        "errors": errors,
        "warnings": [],
        "prompt_chars": len(prompt),
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

    output = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    markdown = (repo_root / args.markdown_output).resolve() if not Path(args.markdown_output).is_absolute() else Path(args.markdown_output)

    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "case_count": report["case_count"],
                "failed_case_count": report["failed_case_count"],
                "retry_required": retry_required,
                "provider_execution_performed": False,
                "patch_application_performed": False,
                "sqlite_write_performed": False,
                "persistent_memory_write_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
