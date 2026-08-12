#!/usr/bin/env python3
"""Smoke-test the agnostic context stack used by megalithic review.

This validator exercises the layered IA-Carmine context artifacts in sequence:

1. agent memory inventory;
2. agnostic tool inventory;
3. transient request context;
4. megalithic review consuming those artifacts through --report-file;
5. signal refinement;
6. PR draft generation.

Default execution is CPU-only/report-only and does not execute providers.
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

DEFAULT_OUTPUT = "output/validation/agnostic_context_stack_smoke.json"
DEFAULT_MARKDOWN = "output/validation/agnostic_context_stack_smoke.md"
DEFAULT_WORK_DIR = "output/validation/agnostic_context_stack_smoke"


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


def check_json_output(repo_root: Path, output: str, expected: dict[str, Any]) -> dict[str, Any]:
    path = repo_path(repo_root, output)
    result: dict[str, Any] = {"path": rel(path, repo_root), "exists": path.exists(), "ok": True, "errors": [], "kind": None, "passed": None}
    if not path.exists():
        result["ok"] = False
        result["errors"].append("missing output")
        return result
    data, error = load_json(path)
    if error or data is None:
        result["ok"] = False
        result["errors"].append(error or "invalid JSON")
        return result
    result["kind"] = data.get("kind")
    result["passed"] = data.get("passed")
    for required in ("schema_version", "kind", "passed"):
        if data.get(required) is None:
            result["ok"] = False
            result["errors"].append(f"missing required field: {required}")
    for key, expected_value in expected.items():
        actual = value_at(data, key)
        if actual != expected_value:
            result["ok"] = False
            result["errors"].append(f"unexpected {key}: expected {expected_value!r}, got {actual!r}")
    return result


def run_step(repo_root: Path, name: str, command: list[str], outputs: dict[str, dict[str, Any]], timeout_seconds: int, dry_run: bool) -> dict[str, Any]:
    step: dict[str, Any] = {"name": name, "command": command, "returncode": None, "ok": True, "errors": [], "stdout_tail": "", "stderr_tail": "", "outputs": []}
    if dry_run:
        step["warnings"] = ["dry-run: command not executed"]
        return step
    returncode, stdout, stderr, error = run_command(command, repo_root, timeout_seconds)
    step["returncode"] = returncode
    step["stdout_tail"] = stdout
    step["stderr_tail"] = stderr
    if error:
        step["errors"].append(error)
    if returncode != 0:
        step["errors"].append(f"command returned {returncode}")
    for output, expected in outputs.items():
        validation = check_json_output(repo_root, output, expected) if output.endswith(".json") else {"path": output, "exists": repo_path(repo_root, output).exists(), "ok": repo_path(repo_root, output).exists(), "errors": []}
        step["outputs"].append(validation)
        if not validation["ok"]:
            step["errors"].extend(f"{validation['path']}: {err}" for err in validation["errors"])
    step["ok"] = not step["errors"]
    return step


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agnostic Context Stack Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Dry run: `{report['dry_run']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Step count: `{report['step_count']}`")
    lines.append("")
    for step in report["steps"]:
        lines.append(f"## {step['name']}")
        lines.append("")
        lines.append(f"- OK: `{step['ok']}`")
        lines.append(f"- Return code: `{step['returncode']}`")
        if step.get("errors"):
            lines.append("")
            lines.append("Errors:")
            for error in step["errors"]:
                lines.append(f"- {error}")
        if step.get("outputs"):
            lines.append("")
            lines.append("Outputs:")
            for item in step["outputs"]:
                lines.append(f"- `{item.get('path')}` ok=`{item.get('ok')}` kind=`{item.get('kind')}` passed=`{item.get('passed')}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--memory-db", default="indexAI/agent_memory/agent_memory.sqlite")
    parser.add_argument("--objective", default="Smoke-test the request-scoped agnostic context stack for megalithic review.")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    py = sys.executable
    work_dir = args.work_dir.replace("\\", "/").rstrip("/")
    memory_json = f"{work_dir}/agent_memory_inventory.json"
    memory_md = f"{work_dir}/agent_memory_inventory.md"
    tool_json = f"{work_dir}/agent_agnostic_tool_inventory.json"
    tool_md = f"{work_dir}/agent_agnostic_tool_inventory.md"
    transient_json = f"{work_dir}/agent_transient_request_context.json"
    transient_md = f"{work_dir}/agent_transient_request_context.md"
    review_json = f"{work_dir}/megalithic_repo_review.json"
    review_md = f"{work_dir}/megalithic_repo_review.md"
    review_props = f"{work_dir}/megalithic_repo_review_proposals.json"
    refined_json = f"{work_dir}/megalithic_refined_review.json"
    refined_md = f"{work_dir}/megalithic_refined_review.md"
    refined_props = f"{work_dir}/megalithic_refined_proposals.json"
    pr_draft_json = f"{work_dir}/megalithic_review_pr_draft.json"
    pr_draft_md = f"{work_dir}/megalithic_review_pr_draft.md"

    step_specs = [
        (
            "agent_memory_inventory",
            [py, "Tools/ai/build_agent_memory_inventory.py", "--repo-root", ".", "--memory-db", args.memory_db, "--objective", args.objective, "--output", memory_json, "--markdown-output", memory_md],
            {memory_json: {"provider_execution_performed": False, "patch_application_performed": False, "guardrails.sqlite_read_only": True}},
        ),
        (
            "agent_agnostic_tool_inventory",
            [py, "Tools/ai/build_agent_agnostic_tool_inventory.py", "--repo-root", ".", "--output", tool_json, "--markdown-output", tool_md],
            {tool_json: {"provider_execution_performed": False, "patch_application_performed": False, "guardrails.report_only": True}},
        ),
        (
            "agent_transient_request_context",
            [py, "Tools/ai/build_agent_transient_request_context.py", "--repo-root", ".", "--objective", args.objective, "--memory-note", args.objective, "--report-file", memory_json, "--report-file", tool_json, "--output", transient_json, "--markdown-output", transient_md],
            {transient_json: {"provider_execution_performed": False, "patch_application_performed": False, "guardrails.request_scoped": True, "persistence.sqlite_write_performed": False}},
        ),
        (
            "megalithic_repo_review_with_agnostic_context",
            [py, "Tools/ai/run_megalithic_repo_review.py", "--repo-root", ".", "--include-all-docs", "--include-all-code", "--include-raw", "--include-output", "--include-index", "--include-sqlite-memory", "--report-file", memory_json, "--report-file", tool_json, "--report-file", transient_json, "--output", review_json, "--markdown-output", review_md, "--proposal-output", review_props],
            {review_json: {"provider_execution_performed": False, "patch_application_performed": False, "guardrails.sqlite_memory_read_only": True}, review_props: {"patch_application_performed": False, "apply_mode": "manual_review_only"}},
        ),
        (
            "megalithic_signal_refinement",
            [py, "Tools/ai/refine_megalithic_review_signals.py", "--review", review_json, "--proposals", review_props, "--output", refined_json, "--proposal-output", refined_props, "--markdown-output", refined_md],
            {refined_json: {"patch_application_performed": False, "guardrails.real_github_pr_created": False}, refined_props: {"patch_application_performed": False, "apply_mode": "manual_review_only"}},
        ),
        (
            "megalithic_pr_draft",
            [py, "Tools/ai/build_megalithic_review_pr_draft.py", "--review", refined_json, "--proposals", refined_props, "--output", pr_draft_json, "--markdown-output", pr_draft_md, "--base-branch", "master", "--title-prefix", "review"],
            {pr_draft_json: {"patch_application_performed": False, "guardrails.real_github_pr_created": False, "guardrails.manual_review_required": True}},
        ),
    ]

    steps = [run_step(repo_root, name, command, outputs, args.timeout_seconds, args.dry_run) for name, command, outputs in step_specs]
    errors = [f"{step['name']}: {error}" for step in steps for error in step.get("errors", [])]
    report = {
        "schema_version": 1,
        "kind": "agnostic_context_stack_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [warning for step in steps for warning in step.get("warnings", [])],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "dry_run": bool(args.dry_run),
        "work_dir": work_dir,
        "step_count": len(steps),
        "steps": steps,
        "guardrails": {
            "provider_execution_default_off": True,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_read_only": True,
            "transient_context_request_scoped": True,
            "output_artifacts_should_not_be_committed": True,
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
