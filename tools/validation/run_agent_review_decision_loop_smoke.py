#!/usr/bin/env python3
"""Smoke-test the agent review decision loop wrapper."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/agent_review_decision_loop_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_decision_loop_smoke.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    except Exception as exc:  # noqa: BLE001 - smoke report should capture unexpected failures.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return {}, "JSON root is not an object"
    return data, None


def build_fixtures(repo_root: Path, work_dir: Path) -> tuple[Path, Path, Path]:
    gpu_path = work_dir / "gpu.json"
    evidence_path = work_dir / "evidence.json"
    orchestrator_path = work_dir / "orchestrator.json"

    evidence = {
        "schema_version": 1,
        "kind": "agent_review_evidence_sufficiency",
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": [],
        "decision": {
            "ready_for_manual_patch_count": 1,
            "sufficient_for_real_pr": True,
        },
        "areas": {
            "doc_code": {
                "items": [
                    {
                        "doc": "AGENTS.md",
                        "reference": "Tools/ai/run_agent_review_decision_loop.py",
                        "existing_candidate": "Tools/ai/build_agent_review_patch_plan.py",
                        "candidate_references": [
                            "Tools/ai/build_deterministic_recommendations.py",
                            "Tools/ai/build_agent_review_patch_plan.py",
                        ],
                        "reason": "Decision loop should turn evidence-ready output into a manual review patch plan.",
                        "confidence": "high",
                        "evidence_sufficient": True,
                        "evidence_files": [
                            {
                                "path": "AGENTS.md",
                                "exists": True,
                                "kind": "markdown",
                                "matched_terms": ["manual review", "evidence"],
                            }
                        ],
                    }
                ]
            }
        },
    }
    gpu = {
        "schema_version": 1,
        "kind": "agent_gpu_deep_planning_supervised",
        "repo_root": str(repo_root),
        "passed": False,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": True,
        "patch_application_performed": False,
        "recommendation_count": 0,
        "recommendations": [],
        "empty_recommendations_reason": "json_parse_failure",
        "evidence_ready_for_manual_patch_count": 1,
    }
    orchestrator = {
        "schema_version": 1,
        "kind": "agent_gpu_npu_parallel_orchestrator",
        "repo_root": str(repo_root),
        "passed": False,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": True,
        "patch_application_performed": False,
        "gpu_output": rel(gpu_path, repo_root),
        "gpu_empty_recommendations_reason": "json_parse_failure",
        "npu_audits": [
            {
                "round": 1,
                "status": "success",
                "classification": "usable_audit_text",
                "runtime_tool_context_seen": True,
                "npu_tool_request_count": 1,
                "npu_runtime_tool_execution_count": 1,
                "npu_runtime_tool_failed_count": 0,
                "npu_runtime_tool_blocked_count": 0,
            }
        ],
    }
    write_fixture(evidence_path, evidence)
    write_fixture(gpu_path, gpu)
    write_fixture(orchestrator_path, orchestrator)
    return evidence_path, orchestrator_path, gpu_path


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Decision Loop Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Recommendation count: `{report.get('recommendation_count')}`")
    lines.append(f"- Patch plan count: `{report.get('patch_plan_count')}`")
    lines.append(f"- Deterministic synthesizer used: `{report.get('deterministic_synthesizer_used')}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- {error}")
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def run_smoke(repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    work_dir = repo_root / "output" / "validation" / "agent_review_decision_loop_smoke"
    evidence_path, orchestrator_path, gpu_path = build_fixtures(repo_root, work_dir)

    loop_output = work_dir / "decision_loop.json"
    loop_markdown = work_dir / "decision_loop.md"
    recommendation_output = work_dir / "deterministic_recommendations.json"
    recommendation_markdown = work_dir / "deterministic_recommendations.md"
    bridge_output = work_dir / "bridge_orchestrator.json"
    patch_plan_output = work_dir / "agent_review_patch_plan.json"
    patch_plan_markdown = work_dir / "agent_review_patch_plan.md"

    command = [
        sys.executable,
        "Tools/ai/run_agent_review_decision_loop.py",
        "--repo-root",
        ".",
        "--evidence",
        str(evidence_path),
        "--orchestrator",
        str(orchestrator_path),
        "--gpu-report",
        str(gpu_path),
        "--recommendations-output",
        str(recommendation_output),
        "--recommendations-markdown",
        str(recommendation_markdown),
        "--bridge-orchestrator-output",
        str(bridge_output),
        "--patch-plan-output",
        str(patch_plan_output),
        "--patch-plan-markdown",
        str(patch_plan_markdown),
        "--output",
        str(loop_output),
        "--markdown-output",
        str(loop_markdown),
        "--min-recommendations",
        "1",
        "--min-patch-plans",
        "1",
    ]
    returncode, stdout, stderr, runner_error = run_command(command, repo_root, timeout_seconds)
    errors: list[str] = []
    warnings: list[str] = []
    if runner_error:
        errors.append(runner_error)
    if returncode != 0:
        errors.append(f"decision loop returned {returncode}")

    decision_loop_report, read_error = load_json(loop_output)
    if read_error:
        errors.append(f"unable to read decision loop output: {read_error}")

    recommendation_count = decision_loop_report.get("recommendation_count")
    patch_plan_count = decision_loop_report.get("patch_plan_count")
    deterministic_used = decision_loop_report.get("deterministic_synthesizer_used")
    fallback_used = decision_loop_report.get("patch_plan_fallback_used")

    if decision_loop_report:
        if decision_loop_report.get("passed") is not True:
            errors.append("decision loop report did not pass")
        if recommendation_count != 1:
            errors.append(f"expected recommendation_count=1, got {recommendation_count!r}")
        if patch_plan_count != 1:
            errors.append(f"expected patch_plan_count=1, got {patch_plan_count!r}")
        if deterministic_used is not True:
            errors.append(f"expected deterministic_synthesizer_used=true, got {deterministic_used!r}")
        if fallback_used is not False:
            errors.append(f"expected patch_plan_fallback_used=false, got {fallback_used!r}")
        if decision_loop_report.get("provider_execution_performed") is not False:
            errors.append("decision loop must not perform provider execution")
        if decision_loop_report.get("patch_application_performed") is not False:
            errors.append("decision loop must not perform patch application")
        warnings.extend(decision_loop_report.get("warnings", []))

    return {
        "schema_version": 1,
        "kind": "agent_review_decision_loop_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "decision_loop_output": rel(loop_output, repo_root),
        "recommendation_count": recommendation_count,
        "patch_plan_count": patch_plan_count,
        "deterministic_synthesizer_used": deterministic_used,
        "patch_plan_fallback_used": fallback_used,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_smoke(repo_root, args.timeout_seconds)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    write_text_report(render_markdown(report), markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
