#!/usr/bin/env python3
"""Smoke-test agent review evidence sufficiency analysis.

This validator runs the evidence-sufficiency analyzer against a refined
megalithic review and validates that the result remains report-only while
classifying patch candidates versus findings that need more context.
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

DEFAULT_REFINED_REVIEW = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review_v3.json"
DEFAULT_REFINED_PROPOSALS = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_proposals_v3.json"
DEFAULT_OUTPUT = "output/validation/agent_review_evidence_sufficiency_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_evidence_sufficiency_smoke.md"
DEFAULT_REPORT_OUTPUT = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_REPORT_MARKDOWN = "output/ai_pipeline/agent_review_evidence_sufficiency.md"


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
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


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
    except Exception as exc:  # noqa: BLE001
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def validate_report(repo_root: Path, path_value: str) -> tuple[list[str], dict[str, Any] | None]:
    path = repo_path(repo_root, path_value)
    errors: list[str] = []
    if not path.exists():
        return [f"missing output: {rel(path, repo_root)}"], None
    data, error = load_json(path)
    if error or data is None:
        return [f"invalid JSON: {error}"], None
    required = ["schema_version", "kind", "passed", "provider_execution_performed", "patch_application_performed", "decision", "areas", "guardrails"]
    for field in required:
        if value_at(data, field) is None:
            errors.append(f"missing required field: {field}")
    expected_values = {
        "kind": "agent_review_evidence_sufficiency",
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "guardrails.report_only": True,
        "guardrails.manual_review_required": True,
    }
    for field, expected in expected_values.items():
        actual = value_at(data, field)
        if actual != expected:
            errors.append(f"unexpected {field}: expected {expected!r}, got {actual!r}")
    return errors, data


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Evidence Sufficiency Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Ready candidates: `{report.get('ready_for_manual_patch_count')}`")
    lines.append(f"- Needs more context: `{report.get('needs_more_context_count')}`")
    lines.append(f"- Sufficient for real PR: `{report.get('sufficient_for_real_pr')}`")
    lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--refined-review", default=DEFAULT_REFINED_REVIEW)
    parser.add_argument("--refined-proposals", default=DEFAULT_REFINED_PROPOSALS)
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--tool-output", default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--tool-markdown-output", default=DEFAULT_REPORT_MARKDOWN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    command = [
        sys.executable,
        "Tools/ai/build_agent_review_evidence_sufficiency.py",
        "--repo-root",
        ".",
        "--refined-review",
        args.refined_review,
        "--refined-proposals",
        args.refined_proposals,
        "--output",
        args.tool_output,
        "--markdown-output",
        args.tool_markdown_output,
    ]
    for report_file in args.report_file:
        command.extend(["--report-file", report_file])

    returncode, stdout, stderr, error = run_command(command, repo_root, args.timeout_seconds)
    errors: list[str] = []
    if error:
        errors.append(error)
    if returncode != 0:
        errors.append(f"command returned {returncode}")
    report_errors, tool_report = validate_report(repo_root, args.tool_output)
    errors.extend(report_errors)

    ready = None
    needs_context = None
    sufficient = None
    if tool_report:
        ready = tool_report.get("decision", {}).get("ready_for_manual_patch_count")
        needs_context = tool_report.get("decision", {}).get("needs_more_context_count")
        sufficient = tool_report.get("decision", {}).get("sufficient_for_real_pr")

    report = {
        "schema_version": 1,
        "kind": "agent_review_evidence_sufficiency_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "tool_output": args.tool_output,
        "tool_markdown_output": args.tool_markdown_output,
        "ready_for_manual_patch_count": ready,
        "needs_more_context_count": needs_context,
        "sufficient_for_real_pr": sufficient,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
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
