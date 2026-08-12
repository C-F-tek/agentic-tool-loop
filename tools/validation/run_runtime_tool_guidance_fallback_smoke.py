#!/usr/bin/env python3
"""Smoke-test deterministic runtime tool fallback wiring.

This validator is report-only. It checks that provider outputs with no usable
tool_requests can be converted into safe deterministic fallback requests through
the existing runtime-tool guidance path, without executing providers, applying
patches, running Blender or writing SQLite databases.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_agent_gpu_deep_planning_review import extract_valid_tool_requests
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_deep_planning_review import extract_valid_tool_requests  # type: ignore


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def run_cases() -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    cases: list[dict[str, Any]] = []

    fallback_inputs = [
        (
            "json_parse_failure_shape",
            {
                "summary": "raw provider response could not be parsed",
                "confidence": "low",
                "recommendations": [],
                "tool_requests": [],
                "missing_evidence": ["model_response_not_valid_json"],
                "next_best_action": "inspect provider output",
            },
        ),
        (
            "schema_mismatch_response_shape",
            {"response": {"message": "I cannot produce a patch plan."}},
        ),
        (
            "context_echo_shape",
            {"files": [{"path": "docs/example.md", "content_preview": "raw context"}]},
        ),
    ]

    for name, parsed in fallback_inputs:
        requests, request_errors = extract_valid_tool_requests(parsed, max_requests=3)
        ok = len(requests) == 3 and not request_errors and all(item.get("source") == "deterministic_fallback" for item in requests)
        if not ok:
            errors.append(f"{name}: expected 3 deterministic fallback requests, got {len(requests)} errors={request_errors}")
        cases.append(
            {
                "name": name,
                "passed": ok,
                "request_count": len(requests),
                "request_tools": [item.get("tool") for item in requests],
                "request_sources": [item.get("source") for item in requests],
                "errors": request_errors,
            }
        )

    provider_request_input = {
        "summary": "provider emitted a valid request",
        "confidence": "medium",
        "recommendations": [],
        "tool_requests": [
            {
                "id": "provider_syntax",
                "tool": "check_python_syntax",
                "reason": "Need syntax baseline.",
                "args": {},
            }
        ],
        "missing_evidence": [],
        "next_best_action": "execute requested tool",
    }
    provider_requests, provider_errors = extract_valid_tool_requests(provider_request_input, max_requests=3)
    provider_ok = len(provider_requests) == 1 and not provider_errors and provider_requests[0].get("source") != "deterministic_fallback"
    if not provider_ok:
        errors.append("provider_valid_request: expected exactly one provider request and no deterministic fallback")
    cases.append(
        {
            "name": "provider_valid_request",
            "passed": provider_ok,
            "request_count": len(provider_requests),
            "request_tools": [item.get("tool") for item in provider_requests],
            "request_sources": [item.get("source") for item in provider_requests],
            "errors": provider_errors,
        }
    )

    recommendation_ready_input = {
        "summary": "recommendation already ready",
        "confidence": "high",
        "recommendations": [
            {
                "id": "ready",
                "area": "validation",
                "status": "ready_for_patch_plan",
                "target_files": ["Tools/validation/example.py"],
                "rationale": "Concrete target exists.",
                "proposed_strategy": "Patch manually.",
                "risk": "low",
                "validation_commands": ["python -m py_compile Tools/validation/example.py"],
                "stop_conditions": ["syntax failure"],
            }
        ],
        "tool_requests": [],
        "missing_evidence": [],
        "next_best_action": "build patch plan",
    }
    ready_requests, ready_errors = extract_valid_tool_requests(recommendation_ready_input, max_requests=3)
    ready_ok = not ready_requests and not ready_errors
    if not ready_ok:
        errors.append("recommendation_ready: expected no fallback when recommendation exists")
    cases.append(
        {
            "name": "recommendation_ready",
            "passed": ready_ok,
            "request_count": len(ready_requests),
            "request_tools": [item.get("tool") for item in ready_requests],
            "request_sources": [item.get("source") for item in ready_requests],
            "errors": ready_errors,
        }
    )

    return cases, errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Runtime Tool Guidance Fallback Smoke", ""]
    for key in ["passed", "case_count", "failed_case_count", "provider_execution_performed", "patch_application_performed", "sqlite_write_performed", "persistent_memory_write_performed"]:
        lines.append(f"- `{key}`: `{report.get(key)}`")
    lines.append("")
    lines.append("## Cases")
    for case in report["cases"]:
        lines.append(f"- `{case['name']}`: passed=`{case['passed']}` requests=`{case['request_count']}` tools=`{case['request_tools']}` sources=`{case['request_sources']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/runtime_tool_guidance_fallback_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/runtime_tool_guidance_fallback_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    cases, errors = run_cases()
    report = {
        "schema_version": 1,
        "kind": "runtime_tool_guidance_fallback_smoke",
        "passed": not errors,
        "case_count": len(cases),
        "failed_case_count": sum(1 for item in cases if not item.get("passed")),
        "errors": errors,
        "warnings": [],
        "cases": cases,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_touched": False,
        "git_write_performed": False,
    }
    output = repo_root / args.output
    markdown_output = repo_root / args.markdown_output
    write_json(output, report)
    write_text(markdown_output, render_markdown(report))
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown_output), "case_count": report["case_count"], "failed_case_count": report["failed_case_count"]}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
