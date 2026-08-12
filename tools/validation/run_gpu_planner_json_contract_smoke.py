#!/usr/bin/env python3
"""Smoke-test GPU planner JSON contract helpers."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.gpu_planner_json_contract import result_to_dict, validate_model_response_contract
except ImportError:  # Script-style execution from Tools/validation.
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.gpu_planner_json_contract import result_to_dict, validate_model_response_contract  # type: ignore


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# GPU Planner JSON Contract Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Case count: `{report['case_count']}`")
    lines.append(f"- Failed case count: `{report['failed_case_count']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    for case in report["cases"]:
        lines.append(f"## `{case['name']}`")
        lines.append("")
        lines.append(f"- Passed: `{case['passed']}`")
        lines.append(f"- Expected reason: `{case['expected_reason']}`")
        lines.append(f"- Reason: `{case['result']['empty_recommendations_reason']}`")
        lines.append(f"- JSON OK: `{case['result']['json_ok']}`")
        lines.append(f"- Schema OK: `{case['result']['schema_ok']}`")
        lines.append(f"- Context echo detected: `{case['result']['context_echo_detected']}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def run_smoke(repo_root: Path) -> dict[str, Any]:
    valid_response = """
    {
      "summary": "valid manual review plan",
      "confidence": "medium",
      "recommendations": [
        {
          "id": "gpu_json_001",
          "area": "validation",
          "status": "ready_for_patch_plan",
          "target_files": ["Tools/ai/run_agent_gpu_deep_planning_review.py"],
          "rationale": "contract hardening is isolated",
          "proposed_strategy": "reuse shared parser and validate recommendation schema",
          "risk": "low",
          "validation_commands": ["python -m py_compile ./Tools/ai/run_agent_gpu_deep_planning_review.py"],
          "stop_conditions": ["stop if parser invents recommendations"]
        }
      ],
      "missing_evidence": [],
      "next_best_action": "manual review"
    }
    """
    context_echo_response = """
    ```json
    {
      "files": [
        {
          "path": "AGENTS.md",
          "content_preview": "# AGENTS.md\\n..."
        }
      ]
    }
    ```
    """
    tool_request_response = """
    {
      "summary": "need runtime tools before patch planning",
      "confidence": "medium",
      "recommendations": [],
      "tool_requests": [
        {
          "id": "python_line_count_inventory",
          "tool": "build_python_line_count_csv",
          "reason": "Need complete Python inventory before selecting refactor targets.",
          "args": {}
        },
        {
          "id": "operational_memory_status",
          "tool": "runtime_sqlite_memory",
          "reason": "Need scratch operational memory status before the next planner round.",
          "args": {"action": "status", "scope": "operational"}
        }
      ],
      "missing_evidence": [],
      "next_best_action": "run broker for requested tools"
    }
    """
    invalid_tool_request_response = """
    {
      "summary": "invalid runtime tool request",
      "confidence": "low",
      "recommendations": [],
      "tool_requests": [
        {
          "id": "free_shell",
          "tool": "shell",
          "reason": "This must be blocked by the contract.",
          "args": {"command": "whoami"}
        }
      ],
      "missing_evidence": [],
      "next_best_action": "reject invalid tool request"
    }
    """
    evidence_ready_no_tool_request_response = """
    {
      "summary": "evidence is ready but the model did not request tools",
      "confidence": "low",
      "recommendations": [],
      "tool_requests": [],
      "missing_evidence": [],
      "next_best_action": "manual review cannot proceed without more concrete evidence"
    }
    """
    malformed_response = "not JSON at all: { missing quoted keys and closing braces"
    schema_mismatch_response = """
    {
      "summary": "valid JSON but wrong shape",
      "confidence": "low",
      "files": [
        {
          "path": "AGENTS.md",
          "content_preview": "# AGENTS.md\\n..."
        }
      ]
    }
    """
    cases = [
        {
            "name": "valid_recommendation",
            "response": valid_response,
            "expected_reason": "",
            "expected_json_ok": True,
            "expected_context_echo": False,
        },
        {
            "name": "context_echo",
            "response": context_echo_response,
            "expected_reason": "context_echo_detected",
            "expected_json_ok": True,
            "expected_context_echo": True,
        },
        {
            "name": "tool_requests_pending",
            "response": tool_request_response,
            "expected_reason": "tool_requests_pending",
            "expected_json_ok": True,
            "expected_context_echo": False,
            "expected_valid_tool_request_count": 2,
        },
        {
            "name": "invalid_tool_request",
            "response": invalid_tool_request_response,
            "expected_reason": "model_output_schema_mismatch",
            "expected_json_ok": True,
            "expected_context_echo": False,
            "expected_valid_tool_request_count": 0,
        },
        {
            "name": "evidence_ready_no_tool_request",
            "response": evidence_ready_no_tool_request_response,
            "expected_reason": "evidence_ready_but_no_tool_requests",
            "expected_json_ok": True,
            "expected_context_echo": False,
            "expected_valid_tool_request_count": 0,
        },
        {
            "name": "malformed_json",
            "response": malformed_response,
            "expected_reason": "json_parse_failure",
            "expected_json_ok": False,
            "expected_context_echo": False,
        },
        {
            "name": "schema_context_echo",
            "response": schema_mismatch_response,
            "expected_reason": "context_echo_detected",
            "expected_json_ok": True,
            "expected_context_echo": True,
        },
    ]

    rendered_cases: list[dict[str, Any]] = []
    for case in cases:
        result = validate_model_response_contract(
            case["response"],
            evidence_ready_for_manual_patch_count=12,
        )
        result_dict = result_to_dict(result)
        expected_valid_tool_request_count = case.get("expected_valid_tool_request_count")
        passed = (
            result.empty_recommendations_reason == case["expected_reason"]
            and result.json_ok is case["expected_json_ok"]
            and result.context_echo_detected is case["expected_context_echo"]
            and (
                expected_valid_tool_request_count is None
                or result.valid_tool_request_count == expected_valid_tool_request_count
            )
        )
        rendered_cases.append(
            {
                "name": case["name"],
                "passed": passed,
                "expected_reason": case["expected_reason"],
                "result": result_dict,
            }
        )

    failed = [case for case in rendered_cases if not case["passed"]]
    return {
        "schema_version": 1,
        "kind": "gpu_planner_json_contract_smoke",
        "generated_at": now_iso(),
        "repo_root": repo_root.as_posix(),
        "passed": not failed,
        "errors": [f"case failed: {case['name']}" for case in failed],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "sqlite_write_performed": False,
        "manual_review_required": True,
        "case_count": len(rendered_cases),
        "failed_case_count": len(failed),
        "cases": rendered_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_smoke(repo_root)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "case_count": report["case_count"],
                "failed_case_count": report["failed_case_count"],
                "patch_application_performed": report["patch_application_performed"],
                "source_writes_performed": report["source_writes_performed"],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
