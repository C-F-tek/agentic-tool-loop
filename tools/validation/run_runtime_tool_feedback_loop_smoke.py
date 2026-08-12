#!/usr/bin/env python3
"""Smoke-test runtime-tool feedback loop context handoff."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_agent_gpu_deep_planning_supervised import (
        append_runtime_tool_feedback_context,
        runtime_tool_feedback_context_report,
    )
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_deep_planning_supervised import (  # type: ignore
        append_runtime_tool_feedback_context,
        runtime_tool_feedback_context_report,
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Runtime Tool Feedback Loop Smoke", ""]
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/runtime_tool_feedback_loop_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/runtime_tool_feedback_loop_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    broker_result = {
        "source": "deterministic_fallback",
        "deterministic_fallback": True,
        "executed": True,
        "broker_output_exists": True,
        "broker_output": "output/ai_runtime_tools/demo/round_001_runtime_tool_broker.json",
        "passed": True,
        "tool_request_count": 2,
        "requested_tool_count": 2,
        "tool_execution_count": 2,
        "blocked_tool_count": 0,
        "failed_tool_count": 0,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "operational_sqlite_write_performed": False,
        "tool_results": [
            {
                "id": "fallback_python_syntax",
                "tool": "check_python_syntax",
                "executed": True,
                "blocked": False,
                "returncode": 0,
                "outputs": {"json_report": "output/validation/python_syntax.json"},
                "summary": {"passed": True, "checked_count": 294, "failed_count": 0},
                "guardrails": {"patch_application_performed": False},
            }
        ],
        "guardrails": {"runtime_tool_broker_report_only": True},
    }

    errors: list[str] = []
    feedback = runtime_tool_feedback_context_report(1, broker_result)
    context_reports: list[dict[str, Any]] = []
    appended = append_runtime_tool_feedback_context(context_reports, 1, broker_result)

    if feedback.get("kind") != "runtime_tool_feedback_context":
        errors.append("feedback kind mismatch")
    if feedback.get("source") != "deterministic_fallback":
        errors.append("feedback source mismatch")
    if not feedback.get("decision", {}).get("feed_into_next_provider_round"):
        errors.append("feedback does not request next-round provider handoff")
    if feedback.get("decision", {}).get("do_not_treat_fallback_as_provider_emitted") is not True:
        errors.append("fallback/provider distinction missing")
    if not appended or len(context_reports) != 1:
        errors.append("append_runtime_tool_feedback_context did not append exactly one report")
    if context_reports and context_reports[0].get("tool_results", [])[0].get("tool") != "check_python_syntax":
        errors.append("tool result was not preserved in compact feedback context")

    report = {
        "schema_version": 1,
        "kind": "runtime_tool_feedback_loop_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "case_count": 1,
        "failed_case_count": 1 if errors else 0,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_touched": False,
        "git_write_performed": False,
        "feedback": feedback,
        "context_report_count": len(context_reports),
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

    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
