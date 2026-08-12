#!/usr/bin/env python3
"""Smoke-test the agent review patch plan builder.

This validator executes the report-only patch-plan builder and checks that it
converts GPU recommendations or evidence-sufficiency fallback candidates into a
manual-review patch plan without applying any patch.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

DEFAULT_ORCHESTRATOR = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator_live.json"
DEFAULT_EVIDENCE = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_TOOL_OUTPUT = "output/patch_specs/agent_review_patch_plan.json"
DEFAULT_TOOL_MARKDOWN = "output/patch_specs/agent_review_patch_plan.md"
DEFAULT_OUTPUT = "output/validation/agent_review_patch_plan_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_patch_plan_smoke.md"


def repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - validation report should capture diagnostics.
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, "JSON root is not an object"
    return data, None


def value_at(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], None
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 - smoke should report unexpected runner failures.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def validate_patch_plan(repo_root: Path, path_value: str, *, min_patch_plans: int, expect_fallback: bool) -> tuple[list[str], list[str], dict[str, Any] | None]:
    path = repo_path(repo_root, path_value)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return [f"missing output: {rel(path, repo_root)}"], warnings, None

    data, error = load_json(path)
    if error or data is None:
        return [f"invalid JSON: {error}"], warnings, None

    required = [
        "schema_version",
        "kind",
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "source_writes_performed",
        "apply_mode",
        "decision",
        "patch_plan_count",
        "patch_plans",
        "guardrails",
    ]
    for field in required:
        if value_at(data, field) is None:
            errors.append(f"missing required field: {field}")

    expected_values = {
        "kind": "agent_review_patch_plan",
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_manual_review_patch_plan",
        "decision.manual_review_required": True,
        "guardrails.report_only": True,
        "guardrails.manual_review_required": True,
        "guardrails.provider_execution_performed": False,
        "guardrails.patch_application_performed": False,
        "guardrails.real_github_pr_created": False,
        "guardrails.sqlite_write_performed": False,
        "guardrails.persistent_memory_write_performed": False,
        "guardrails.blender_runtime_execution_performed": False,
        "guardrails.npu_primary_advisory": False,
        "guardrails.openvino_gpu_primary_lane": False,
    }
    for field, expected in expected_values.items():
        actual = value_at(data, field)
        if actual != expected:
            errors.append(f"unexpected {field}: expected {expected!r}, got {actual!r}")

    patch_plan_count = data.get("patch_plan_count")
    patch_plans = data.get("patch_plans")
    if not isinstance(patch_plan_count, int):
        errors.append("patch_plan_count must be an integer")
    elif patch_plan_count < min_patch_plans:
        errors.append(f"patch_plan_count below minimum: expected >= {min_patch_plans}, got {patch_plan_count}")

    if not isinstance(patch_plans, list):
        errors.append("patch_plans must be a list")
    elif isinstance(patch_plan_count, int) and len(patch_plans) != patch_plan_count:
        errors.append(f"patch_plans length mismatch: count={patch_plan_count}, len={len(patch_plans)}")
    else:
        for index, plan in enumerate(patch_plans if isinstance(patch_plans, list) else [], start=1):
            if not isinstance(plan, dict):
                errors.append(f"patch_plans[{index}] is not an object")
                continue
            for field in ["id", "source", "area", "status", "target_files", "rationale", "edit_strategy", "manual_review_required"]:
                if field not in plan:
                    errors.append(f"patch_plans[{index}] missing {field}")
            if plan.get("manual_review_required") is not True:
                errors.append(f"patch_plans[{index}] manual_review_required must be true")
            target_files = plan.get("target_files")
            if not isinstance(target_files, list) or not target_files:
                errors.append(f"patch_plans[{index}] target_files must be a non-empty list")
            for target in target_files if isinstance(target_files, list) else []:
                target_text = str(target).replace("\\", "/")
                if target_text.startswith("output/"):
                    errors.append(f"patch_plans[{index}] targets output/**: {target_text}")

    fallback_used = value_at(data, "decision.fallback_used")
    if expect_fallback and fallback_used is not True:
        errors.append(f"expected fallback_used true, got {fallback_used!r}")
    if not expect_fallback and fallback_used is True:
        warnings.append("fallback_used is true; GPU planner produced no usable ready recommendation")

    return errors, warnings, data


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Patch Plan Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Patch plan count: `{report.get('patch_plan_count')}`")
    lines.append(f"- Fallback used: `{report.get('fallback_used')}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- {error}")
        lines.append("")
    if report.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--orchestrator", default=DEFAULT_ORCHESTRATOR)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--min-patch-plans", type=int, default=1)
    parser.add_argument("--expect-fallback", action="store_true")
    parser.add_argument("--tool-output", default=DEFAULT_TOOL_OUTPUT)
    parser.add_argument("--tool-markdown-output", default=DEFAULT_TOOL_MARKDOWN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    command = [
        sys.executable,
        "Tools/ai/build_agent_review_patch_plan.py",
        "--repo-root",
        ".",
        "--orchestrator",
        args.orchestrator,
        "--evidence",
        args.evidence,
        "--output",
        args.tool_output,
        "--markdown-output",
        args.tool_markdown_output,
    ]

    returncode, stdout, stderr, error = run_command(command, repo_root, args.timeout_seconds)
    errors: list[str] = []
    warnings: list[str] = []
    if error:
        errors.append(error)
    if returncode != 0:
        errors.append(f"command returned {returncode}")

    report_errors, report_warnings, tool_report = validate_patch_plan(
        repo_root,
        args.tool_output,
        min_patch_plans=args.min_patch_plans,
        expect_fallback=args.expect_fallback,
    )
    errors.extend(report_errors)
    warnings.extend(report_warnings)

    patch_plan_count = None
    fallback_used = None
    if tool_report:
        patch_plan_count = tool_report.get("patch_plan_count")
        fallback_used = value_at(tool_report, "decision.fallback_used")

    report = {
        "schema_version": 1,
        "kind": "agent_review_patch_plan_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "tool_output": args.tool_output,
        "tool_markdown_output": args.tool_markdown_output,
        "patch_plan_count": patch_plan_count,
        "fallback_used": fallback_used,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
        },
    }

    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
