#!/usr/bin/env python3
"""Smoke-test deterministic NPU runtime-tool fallback request generation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_npu_gpu_deep_review_auditor import (
        build_npu_deterministic_tool_fallback_requests,
        should_use_npu_deterministic_tool_fallback,
    )
    from Tools.ai.runtime_tool_guidance import validate_runtime_tool_request_object
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_npu_gpu_deep_review_auditor import (  # type: ignore
        build_npu_deterministic_tool_fallback_requests,
        should_use_npu_deterministic_tool_fallback,
    )
    from Tools.ai.runtime_tool_guidance import validate_runtime_tool_request_object  # type: ignore


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# NPU Runtime Tool Fallback Smoke", ""]
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
    parser.add_argument("--output", default="output/validation/npu_runtime_tool_fallback_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/npu_runtime_tool_fallback_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    runtime_context = [{"kind": "runtime_tool_feedback_context", "tool_results": [{"tool": "check_python_syntax"}]}]
    should_use = should_use_npu_deterministic_tool_fallback(
        run_npu=True,
        metadata_only=False,
        runtime_tool_context_reports=runtime_context,
        tool_requests=[],
        classification="usable_audit_text",
        disabled=False,
    )
    requests = build_npu_deterministic_tool_fallback_requests(
        classification="usable_audit_text",
        runtime_tool_context_reports=runtime_context,
        max_requests=3,
    )
    errors: list[str] = []
    if not should_use:
        errors.append("NPU deterministic fallback trigger returned false")
    if not requests:
        errors.append("NPU deterministic fallback generated no requests")
    for index, request in enumerate(requests, start=1):
        validation_errors = validate_runtime_tool_request_object(request, index)
        if validation_errors:
            errors.extend(validation_errors)
        if request.get("source") != "npu_deterministic_fallback":
            errors.append(f"request {index} source mismatch: {request.get('source')}")
        if not str(request.get("id") or "").startswith("npu_"):
            errors.append(f"request {index} id is not NPU-prefixed: {request.get('id')}")

    disabled = should_use_npu_deterministic_tool_fallback(
        run_npu=True,
        metadata_only=False,
        runtime_tool_context_reports=runtime_context,
        tool_requests=[],
        classification="usable_audit_text",
        disabled=True,
    )
    if disabled:
        errors.append("NPU fallback trigger ignored disabled=True")

    report = {
        "schema_version": 1,
        "kind": "npu_runtime_tool_fallback_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "case_count": 2,
        "failed_case_count": 1 if errors else 0,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_touched": False,
        "git_write_performed": False,
        "request_count": len(requests),
        "requests": requests,
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
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown), "request_count": len(requests)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
