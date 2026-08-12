#!/usr/bin/env python3
"""Smoke-test the agent review patch bundle builder."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/agent_review_patch_bundle_builder_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_patch_bundle_builder_smoke.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return {}, "JSON root is not an object"
    return data, None


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], None
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Patch Bundle Builder Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Return code: `{report['returncode']}`")
    lines.append(f"- Operation count: `{report.get('operation_count')}`")
    lines.append(f"- Skipped candidate count: `{report.get('skipped_candidate_count')}`")
    lines.append(f"- Bundle ZIP exists: `{report.get('bundle_zip_exists')}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def build_fixture_patch_plan(repo_root: Path, patch_plan_path: Path) -> None:
    patch_plan = {
        "schema_version": 1,
        "kind": "agent_review_patch_plan",
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_manual_review_patch_plan",
        "decision": {
            "ready_for_manual_review": True,
            "patch_plan_count": 2,
            "fallback_used": False,
            "manual_review_required": True,
        },
        "patch_plan_count": 2,
        "patch_plans": [
            {
                "id": "smoke_doc_patch",
                "source": "smoke",
                "area": "doc_doc",
                "status": "ready_for_manual_review",
                "target_files": ["AGENTS.md"],
                "rationale": "Smoke test verifies managed Markdown bundle operation generation.",
                "edit_strategy": "Append or replace one managed note block without touching runtime code.",
                "risk": "low",
                "validation_commands": ["git diff --check", "git status --short"],
                "stop_conditions": ["Stop if managed marker replacement is not idempotent."],
                "manual_review_required": True,
            },
            {
                "id": "smoke_code_patch_manual_only",
                "source": "smoke",
                "area": "code",
                "status": "ready_for_manual_review",
                "target_files": ["Tools/ai/run_agent_review_decision_loop.py"],
                "rationale": "Non-Markdown targets must be skipped by the automatic bundle builder.",
                "edit_strategy": "Manual review only.",
                "risk": "medium",
                "validation_commands": ["python -m py_compile Tools/ai/run_agent_review_decision_loop.py"],
                "stop_conditions": ["Stop if builder tries to mutate Python source."],
                "manual_review_required": True,
            },
        ],
        "skipped_candidates": [],
        "guardrails": {
            "report_only": True,
            "manual_review_required": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }
    write_json(patch_plan_path, patch_plan)


def run_smoke(repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    work_dir = repo_root / "output" / "validation" / "agent_review_patch_bundle_builder_smoke"
    patch_plan_path = work_dir / "agent_review_patch_plan.json"
    builder_output = work_dir / "builder.json"
    builder_markdown = work_dir / "builder.md"
    bundle_dir = work_dir / "bundles"
    build_fixture_patch_plan(repo_root, patch_plan_path)

    command = [
        sys.executable,
        "Tools/ai/build_agent_review_patch_bundle.py",
        "--repo-root",
        ".",
        "--patch-plan",
        str(patch_plan_path),
        "--output-dir",
        str(bundle_dir),
        "--basename",
        "smoke_patch_bundle",
        "--stamp",
        "smoke",
        "--output",
        str(builder_output),
        "--markdown-output",
        str(builder_markdown),
        "--write-bundle",
    ]
    returncode, stdout, stderr, runner_error = run_command(command, repo_root, timeout_seconds)
    errors: list[str] = []
    if runner_error:
        errors.append(runner_error)
    if returncode != 0:
        errors.append(f"builder returned {returncode}")

    builder_report, read_error = load_json(builder_output)
    if read_error:
        errors.append(f"unable to read builder output: {read_error}")

    bundle_zip = repo_root / str(builder_report.get("bundle_zip", "")) if builder_report.get("bundle_zip") else Path("")
    if builder_report:
        if builder_report.get("passed") is not True:
            errors.append("builder report did not pass")
        if builder_report.get("operation_count") != 1:
            errors.append(f"expected operation_count=1, got {builder_report.get('operation_count')!r}")
        if builder_report.get("skipped_candidate_count") != 1:
            errors.append(f"expected skipped_candidate_count=1, got {builder_report.get('skipped_candidate_count')!r}")
        if builder_report.get("patch_application_performed") is not False:
            errors.append("builder must not apply patches")
        if builder_report.get("sqlite_write_performed") is not False:
            errors.append("builder must not write SQLite")
        if not bundle_zip.exists():
            errors.append(f"bundle ZIP missing: {bundle_zip}")

    return {
        "schema_version": 1,
        "kind": "agent_review_patch_bundle_builder_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "builder_output": rel(builder_output, repo_root),
        "operation_count": builder_report.get("operation_count") if builder_report else None,
        "skipped_candidate_count": builder_report.get("skipped_candidate_count") if builder_report else None,
        "bundle_zip": builder_report.get("bundle_zip") if builder_report else "",
        "bundle_zip_exists": bundle_zip.exists() if str(bundle_zip) else False,
        "guardrails": {
            "report_only_builder": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--timeout-seconds", type=int, default=120)
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
