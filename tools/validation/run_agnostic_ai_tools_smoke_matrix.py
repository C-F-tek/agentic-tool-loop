#!/usr/bin/env python3
"""Run a sequential smoke matrix for agnostic IA-Carmine AI tools.

The matrix executes report-only/manual-review tools by default and validates the
artifacts they produce. Expectations are applied per output artifact because
review reports, proposal manifests and PR-draft artifacts intentionally expose
different guardrail fields.

Default behavior performs no provider execution and no patch application.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:  # Allows package-style imports during external checks.
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/agnostic_ai_tools_smoke_matrix.json"
DEFAULT_MARKDOWN = "output/validation/agnostic_ai_tools_smoke_matrix.md"
DEFAULT_WORK_DIR = "output/validation/agnostic_ai_tools_smoke_matrix"
COMMON_JSON_FIELDS = ("schema_version", "kind", "passed")


@dataclass(frozen=True)
class SmokeStep:
    """One sequential smoke test step."""

    name: str
    command: list[str]
    expected_outputs: list[str]
    required_fields: tuple[str, ...] = COMMON_JSON_FIELDS
    expected_values: dict[str, Any] = field(default_factory=dict)
    expected_values_by_output: dict[str, dict[str, Any]] = field(default_factory=dict)
    required_fields_by_output: dict[str, tuple[str, ...]] = field(default_factory=dict)
    allow_nonzero: bool = False
    heavy: bool = False
    provider_live: bool = False
    workflow: bool = False


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
    except Exception as exc:  # noqa: BLE001 - smoke validation report.
        return None, f"{type(exc).__name__}: {exc}"


def value_at(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def expected_for_output(step: SmokeStep, output: str) -> dict[str, Any]:
    """Return expected values for a specific output artifact."""
    return step.expected_values_by_output.get(output, step.expected_values)


def required_for_output(step: SmokeStep, output: str) -> tuple[str, ...]:
    """Return required fields for a specific output artifact."""
    return step.required_fields_by_output.get(output, step.required_fields)


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
    except Exception as exc:  # noqa: BLE001 - matrix smoke runner.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def validate_output(
    *,
    path: Path,
    repo_root: Path,
    required_fields: tuple[str, ...],
    expected_values: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": rel(path, repo_root),
        "exists": path.exists(),
        "ok": True,
        "errors": [],
        "kind": None,
        "passed": None,
    }
    if not path.exists():
        result["ok"] = False
        result["errors"].append("missing output")
        return result
    if path.suffix.lower() != ".json":
        return result
    data, error = load_json(path)
    if error or data is None:
        result["ok"] = False
        result["errors"].append(error or "invalid JSON")
        return result
    result["kind"] = data.get("kind")
    result["passed"] = data.get("passed")
    for field_name in required_fields:
        if value_at(data, field_name) is None:
            result["ok"] = False
            result["errors"].append(f"missing required field: {field_name}")
    for field_name, expected in expected_values.items():
        actual = value_at(data, field_name)
        if actual != expected:
            result["ok"] = False
            result["errors"].append(f"unexpected {field_name}: expected {expected!r}, got {actual!r}")
    return result


def build_steps(args: argparse.Namespace) -> list[SmokeStep]:
    py = sys.executable
    work_dir = args.work_dir.replace("\\", "/").rstrip("/")
    memory_inventory_json = f"{work_dir}/agent_memory_inventory.json"
    memory_inventory_md = f"{work_dir}/agent_memory_inventory.md"
    megalithic_json = f"{work_dir}/megalithic_repo_review.json"
    megalithic_md = f"{work_dir}/megalithic_repo_review.md"
    megalithic_proposals = f"{work_dir}/megalithic_repo_review_proposals.json"
    refined_json = f"{work_dir}/megalithic_refined_review.json"
    refined_md = f"{work_dir}/megalithic_refined_review.md"
    refined_proposals = f"{work_dir}/megalithic_refined_proposals.json"
    pr_draft_json = f"{work_dir}/megalithic_review_pr_draft.json"
    pr_draft_md = f"{work_dir}/megalithic_review_pr_draft.md"

    steps = [
        SmokeStep(
            name="agent_memory_inventory",
            command=[
                py,
                "Tools/ai/build_agent_memory_inventory.py",
                "--repo-root",
                ".",
                "--memory-db",
                args.memory_db,
                "--objective",
                "Smoke-test generic agent memory inventory for IA-Carmine orchestration.",
                "--output",
                memory_inventory_json,
                "--markdown-output",
                memory_inventory_md,
            ],
            expected_outputs=[memory_inventory_json, memory_inventory_md],
            expected_values_by_output={
                memory_inventory_json: {
                    "provider_execution_performed": False,
                    "patch_application_performed": False,
                    "guardrails.sqlite_read_only": True,
                }
            },
        ),
        SmokeStep(
            name="megalithic_repo_review_cpu",
            command=[
                py,
                "Tools/ai/run_megalithic_repo_review.py",
                "--repo-root",
                ".",
                "--include-all-docs",
                "--include-all-code",
                "--include-raw",
                "--include-output",
                "--include-index",
                "--include-sqlite-memory",
                "--output",
                megalithic_json,
                "--markdown-output",
                megalithic_md,
                "--proposal-output",
                megalithic_proposals,
            ],
            expected_outputs=[megalithic_json, megalithic_md, megalithic_proposals],
            expected_values_by_output={
                megalithic_json: {
                    "provider_execution_performed": False,
                    "patch_application_performed": False,
                    "guardrails.sqlite_memory_read_only": True,
                },
                megalithic_proposals: {
                    "provider_execution_performed": False,
                    "patch_application_performed": False,
                    "apply_mode": "manual_review_only",
                },
            },
            heavy=True,
        ),
        SmokeStep(
            name="megalithic_signal_refinement",
            command=[
                py,
                "Tools/ai/refine_megalithic_review_signals.py",
                "--review",
                megalithic_json,
                "--proposals",
                megalithic_proposals,
                "--output",
                refined_json,
                "--proposal-output",
                refined_proposals,
                "--markdown-output",
                refined_md,
            ],
            expected_outputs=[refined_json, refined_md, refined_proposals],
            expected_values_by_output={
                refined_json: {
                    "patch_application_performed": False,
                    "guardrails.real_github_pr_created": False,
                },
                refined_proposals: {
                    "patch_application_performed": False,
                    "apply_mode": "manual_review_only",
                },
            },
        ),
        SmokeStep(
            name="megalithic_pr_draft",
            command=[
                py,
                "Tools/ai/build_megalithic_review_pr_draft.py",
                "--review",
                refined_json,
                "--proposals",
                refined_proposals,
                "--output",
                pr_draft_json,
                "--markdown-output",
                pr_draft_md,
                "--base-branch",
                "master",
                "--title-prefix",
                "review",
            ],
            expected_outputs=[pr_draft_json, pr_draft_md],
            expected_values_by_output={
                pr_draft_json: {
                    "patch_application_performed": False,
                    "guardrails.real_github_pr_created": False,
                    "guardrails.manual_review_required": True,
                }
            },
        ),
    ]

    if args.include_ollama_live:
        live_json = f"{work_dir}/megalithic_repo_review_ollama_live.json"
        live_md = f"{work_dir}/megalithic_repo_review_ollama_live.md"
        live_proposals = f"{work_dir}/megalithic_repo_review_ollama_live_proposals.json"
        steps.append(
            SmokeStep(
                name="megalithic_repo_review_ollama_live",
                command=[
                    py,
                    "Tools/ai/run_megalithic_repo_review.py",
                    "--repo-root",
                    ".",
                    "--include-all-docs",
                    "--include-all-code",
                    "--include-raw",
                    "--include-output",
                    "--include-index",
                    "--include-sqlite-memory",
                    "--use-ollama",
                    "--ollama-max-new-tokens",
                    str(args.ollama_max_new_tokens),
                    "--output",
                    live_json,
                    "--markdown-output",
                    live_md,
                    "--proposal-output",
                    live_proposals,
                ],
                expected_outputs=[live_json, live_md, live_proposals],
                expected_values_by_output={
                    live_json: {
                        "provider_execution_performed": True,
                        "patch_application_performed": False,
                    },
                    live_proposals: {
                        "provider_execution_performed": True,
                        "patch_application_performed": False,
                        "apply_mode": "manual_review_only",
                    },
                },
                heavy=True,
                provider_live=True,
            )
        )

    if args.include_workflow:
        workflow_summary = "output/ai_pipeline/local_ai_core_tool_activation_summary.json"
        steps.append(
            SmokeStep(
                name="local_ai_core_tool_activation_workflow",
                command=[
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    ".\\Tools\\workflow\\run_local_ai_core_tool_activation.ps1",
                    "-RunMegalithicReview",
                ],
                expected_outputs=[workflow_summary],
                expected_values_by_output={
                    workflow_summary: {
                        "patch_application_performed": False,
                        "run_megalithic_review": True,
                    }
                },
                heavy=True,
                workflow=True,
            )
        )
    return steps


def run_step(step: SmokeStep, repo_root: Path, timeout_seconds: int, *, dry_run: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": step.name,
        "command": step.command,
        "heavy": step.heavy,
        "provider_live": step.provider_live,
        "workflow": step.workflow,
        "returncode": None,
        "ok": True,
        "errors": [],
        "warnings": [],
        "stdout_tail": "",
        "stderr_tail": "",
        "outputs": [],
    }
    if dry_run:
        result["warnings"].append("dry-run: command not executed")
        return result

    returncode, stdout, stderr, error = run_command(step.command, repo_root, timeout_seconds)
    result["returncode"] = returncode
    result["stdout_tail"] = stdout
    result["stderr_tail"] = stderr
    if error:
        result["errors"].append(error)
    if returncode != 0 and not step.allow_nonzero:
        result["errors"].append(f"command returned {returncode}")

    for output in step.expected_outputs:
        validation = validate_output(
            path=repo_path(repo_root, output),
            repo_root=repo_root,
            required_fields=required_for_output(step, output) if output.endswith(".json") else (),
            expected_values=expected_for_output(step, output) if output.endswith(".json") else {},
        )
        result["outputs"].append(validation)
        if not validation["ok"]:
            result["errors"].extend(f"{validation['path']}: {err}" for err in validation["errors"])

    result["ok"] = not result["errors"]
    return result


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agnostic AI Tools Smoke Matrix", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Dry run: `{report['dry_run']}`")
    lines.append(f"- Include Ollama live: `{report['include_ollama_live']}`")
    lines.append(f"- Include workflow: `{report['include_workflow']}`")
    lines.append(f"- Step count: `{report['step_count']}`")
    lines.append("")
    for step in report["steps"]:
        lines.append(f"## {step['name']}")
        lines.append("")
        lines.append(f"- OK: `{step['ok']}`")
        lines.append(f"- Return code: `{step['returncode']}`")
        lines.append(f"- Provider live: `{step['provider_live']}`")
        lines.append(f"- Workflow: `{step['workflow']}`")
        lines.append("")
        lines.append("Command:")
        lines.append("")
        lines.append("```text")
        lines.append(" ".join(step["command"]))
        lines.append("```")
        if step["errors"]:
            lines.append("")
            lines.append("Errors:")
            for error in step["errors"]:
                lines.append(f"- {error}")
        if step["outputs"]:
            lines.append("")
            lines.append("Outputs:")
            for output in step["outputs"]:
                lines.append(f"- `{output['path']}` ok=`{output['ok']}` kind=`{output.get('kind')}` passed=`{output.get('passed')}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--memory-db", default="indexAI/agent_memory/agent_memory.sqlite")
    parser.add_argument("--include-ollama-live", action="store_true")
    parser.add_argument("--ollama-max-new-tokens", type=int, default=1800)
    parser.add_argument("--include-workflow", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    steps = build_steps(args)
    results = [run_step(step, repo_root, args.timeout_seconds, dry_run=args.dry_run) for step in steps]
    errors = [f"{step['name']}: {error}" for step in results for error in step.get("errors", [])]
    report = {
        "schema_version": 1,
        "kind": "agnostic_ai_tools_smoke_matrix",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [warning for step in results for warning in step.get("warnings", [])],
        "provider_execution_performed": bool(args.include_ollama_live),
        "patch_application_performed": False,
        "source_writes_performed": False,
        "dry_run": bool(args.dry_run),
        "include_ollama_live": bool(args.include_ollama_live),
        "include_workflow": bool(args.include_workflow),
        "work_dir": args.work_dir.replace("\\", "/"),
        "step_count": len(results),
        "steps": results,
        "guardrails": {
            "provider_execution_default_off": True,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_read_only": True,
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
