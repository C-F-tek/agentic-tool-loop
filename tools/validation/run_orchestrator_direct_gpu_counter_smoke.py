#!/usr/bin/env python3
"""Smoke-test orchestrator propagation of direct GPU runtime-tool counters."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import (
        apply_orchestrator_direct_gpu_and_lane_diagnostics,
        effective_npu_auditor_every_rounds,
        npu_lane_diagnostics,
    )
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import (  # type: ignore
        apply_orchestrator_direct_gpu_and_lane_diagnostics,
        effective_npu_auditor_every_rounds,
        npu_lane_diagnostics,
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Orchestrator Direct GPU Counter Smoke", ""]
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
    parser.add_argument("--output", default="output/validation/orchestrator_direct_gpu_counter_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/orchestrator_direct_gpu_counter_smoke.md")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    runtime_args = SimpleNamespace(
        run_npu_auditor_provider=True,
        npu_auditor_every_rounds=2,
        npu_slow_audit_threshold_seconds=60.0,
        npu_slow_auditor_every_rounds=5,
    )
    started = datetime.now() - timedelta(seconds=90)
    audit_records = [
        {
            "round": 1,
            "status": "finished",
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "classification": "usable_audit_text",
            "provider_execution_succeeded": True,
            "returncode": 0,
        }
    ]
    gpu_report = {
        "provider_execution_performed": True,
        "round_count": 6,
        "recommendation_count": 0,
        "empty_recommendations_reason": "model_output_schema_mismatch",
        "runtime_tool_bootstrap_request_count": 7,
        "runtime_tool_bootstrap_execution_count": 7,
        "runtime_tool_request_count": 31,
        "runtime_tool_execution_count": 31,
        "runtime_tool_failed_count": 0,
        "runtime_tool_blocked_count": 0,
        "runtime_tool_provider_request_count": 24,
        "runtime_tool_provider_request_execution_count": 24,
        "runtime_tool_feedback_context_report_count": 6,
        "deterministic_runtime_tool_fallback_request_count": 0,
        "deterministic_runtime_tool_fallback_execution_count": 0,
    }
    report = {
        "runtime_tool_provider_request_count": 0,
        "runtime_tool_provider_request_execution_count": 0,
        "gpu_orchestrated_runtime_tool_request_count": 0,
        "gpu_orchestrated_runtime_tool_execution_count": 0,
        "npu_runtime_tool_request_count": 0,
        "npu_runtime_tool_execution_count": 0,
        "deterministic_runtime_tool_fallback_execution_count": 0,
        "decision": {},
        "gpu_summary": {},
    }

    apply_orchestrator_direct_gpu_and_lane_diagnostics(
        report,
        args=runtime_args,
        gpu_report=gpu_report,
        audit_records=audit_records,
    )
    lane = npu_lane_diagnostics(runtime_args, audit_records)
    effective_every = effective_npu_auditor_every_rounds(runtime_args, audit_records)

    errors: list[str] = []
    if report.get("runtime_tool_provider_request_execution_count") != 24:
        errors.append("direct GPU provider request execution count was not propagated")
    if report.get("runtime_tool_feedback_context_report_count") != 6:
        errors.append("GPU feedback context report count was not propagated")
    if report.get("gpu_direct_runtime_tool_execution_count") != 24:
        errors.append("direct GPU runtime execution count should exclude bootstrap")
    if report.get("gpu_lane_mode") != "primary_fast_loop":
        errors.append("GPU lane mode was not set")
    if report.get("npu_lane_mode") != "slow":
        errors.append("NPU lane should be classified as slow for 90s audit")
    if effective_every != 5 or lane.get("effective_auditor_every_rounds") != 5:
        errors.append("adaptive NPU every-rounds value was not promoted to slow setting")
    if report.get("decision", {}).get("runtime_tool_feedback_context_report_count") != 6:
        errors.append("decision feedback count was not propagated")

    output_report = {
        "schema_version": 1,
        "kind": "orchestrator_direct_gpu_counter_smoke",
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
        "report": report,
        "npu_lane": lane,
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
    write_json(output, output_report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(output_report), encoding="utf-8")
    print(json.dumps({"passed": output_report["passed"], "output": str(output), "markdown": str(markdown)}, indent=2, ensure_ascii=False))
    return 0 if output_report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
