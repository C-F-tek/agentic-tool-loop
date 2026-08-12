#!/usr/bin/env python3
"""Run the standard full validation loop for agent review patch plans.

The loop validates the patch-plan builder output, runs the smallest relevant
repository validators, emits a compact Git-trackable evidence bundle under
``docs/LOCAL_VALIDATION_EVIDENCE/`` and validates that bundle.

It is intentionally provider-free and patch-free. It does not run Blender,
Ollama, OpenVINO, GPU/NPU providers, patch runners or GitHub PR actions.
"""
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
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

DEFAULT_ORCHESTRATOR = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator_live.json"
DEFAULT_EVIDENCE = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_PATCH_PLAN = "output/patch_specs/agent_review_patch_plan.json"
DEFAULT_PATCH_PLAN_MARKDOWN = "output/patch_specs/agent_review_patch_plan.md"
DEFAULT_SMOKE = "output/validation/agent_review_patch_plan_smoke.json"
DEFAULT_SMOKE_MARKDOWN = "output/validation/agent_review_patch_plan_smoke.md"
DEFAULT_DOCS_LINKS = "output/validation/docs_links.json"
DEFAULT_PYTHON_SYNTAX = "output/validation/python_syntax.json"
DEFAULT_REPORT_CONTRACT = "output/validation/validation_report_contract.json"
DEFAULT_BUNDLE_BASENAME = "agent_review_doc_patch_plan_evidence"
DEFAULT_EVIDENCE_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"
DEFAULT_BUNDLE_VALIDATION = "output/validation/agent_review_doc_patch_plan_evidence_bundle_validation.json"
DEFAULT_OUTPUT = "output/validation/agent_review_patch_plan_full_validation.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_patch_plan_full_validation.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - full validation report captures diagnostics.
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def value_at(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    started = datetime.now().isoformat(timespec="seconds")
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
        return {
            "command": command,
            "started_at": started,
            "returncode": completed.returncode,
            "ok": completed.returncode == 0,
            "stdout_tail": (completed.stdout or "")[-12000:],
            "stderr_tail": (completed.stderr or "")[-12000:],
            "error": "",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "started_at": started,
            "returncode": 124,
            "ok": False,
            "stdout_tail": exc.stdout or "",
            "stderr_tail": exc.stderr or "",
            "error": f"TimeoutExpired: {timeout_seconds}s",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "command": command,
            "started_at": started,
            "returncode": 1,
            "ok": False,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def bundle_paths(repo_root: Path, output_dir: str, basename: str) -> tuple[Path, Path]:
    directory = repo_path(repo_root, output_dir)
    return directory / f"{basename}.json", directory / f"{basename}.md"


def summarize_artifact(path: Path, repo_root: Path) -> dict[str, Any]:
    data, error = load_json(path) if path.exists() else (None, "missing")
    summary: dict[str, Any] = {
        "path": rel(path, repo_root),
        "exists": path.exists(),
        "json_ok": data is not None,
        "error": error or "",
    }
    if data:
        for key in (
            "schema_version",
            "kind",
            "passed",
            "provider_execution_performed",
            "patch_application_performed",
            "source_writes_performed",
            "apply_mode",
            "patch_plan_count",
            "fallback_used",
            "bundle_count",
        ):
            if key in data:
                summary[key] = data.get(key)
        decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
        if decision:
            summary["decision"] = {
                key: decision.get(key)
                for key in (
                    "ready_for_manual_review",
                    "patch_plan_count",
                    "fallback_used",
                    "gpu_recommendation_count",
                    "evidence_ready_for_manual_patch_count",
                    "manual_review_required",
                    "provider_execution_seen",
                    "selected_chunks_evidence_seen",
                )
                if key in decision
            }
    return summary


def validate_expected_outputs(
    *,
    repo_root: Path,
    patch_plan_path: Path,
    smoke_path: Path,
    bundle_json: Path,
    bundle_md: Path,
    min_patch_plans: int,
    expect_fallback: bool,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    artifacts = {
        "patch_plan": summarize_artifact(patch_plan_path, repo_root),
        "smoke": summarize_artifact(smoke_path, repo_root),
        "bundle_json": summarize_artifact(bundle_json, repo_root),
        "bundle_markdown": {
            "path": rel(bundle_md, repo_root),
            "exists": bundle_md.exists(),
            "json_ok": None,
            "error": "" if bundle_md.exists() else "missing",
        },
    }

    patch_plan, patch_error = load_json(patch_plan_path) if patch_plan_path.exists() else (None, "missing")
    if patch_error or patch_plan is None:
        errors.append(f"patch plan unreadable: {patch_error}")
    else:
        count = patch_plan.get("patch_plan_count")
        if not isinstance(count, int) or count < min_patch_plans:
            errors.append(f"patch_plan_count below minimum: expected >= {min_patch_plans}, got {count!r}")
        fallback = value_at(patch_plan, "decision.fallback_used")
        if expect_fallback and fallback is not True:
            errors.append(f"expected patch plan fallback_used=true, got {fallback!r}")
        if patch_plan.get("provider_execution_performed") is not False:
            errors.append("patch plan provider_execution_performed must be false")
        if patch_plan.get("patch_application_performed") is not False:
            errors.append("patch plan patch_application_performed must be false")

    smoke, smoke_error = load_json(smoke_path) if smoke_path.exists() else (None, "missing")
    if smoke_error or smoke is None:
        errors.append(f"smoke report unreadable: {smoke_error}")
    elif smoke.get("passed") is not True:
        errors.append("agent_review_patch_plan_smoke did not pass")

    if not bundle_json.exists():
        errors.append(f"evidence bundle JSON missing: {rel(bundle_json, repo_root)}")
    if not bundle_md.exists():
        errors.append(f"evidence bundle Markdown missing: {rel(bundle_md, repo_root)}")

    bundle, bundle_error = load_json(bundle_json) if bundle_json.exists() else (None, "missing")
    if bundle_error or bundle is None:
        errors.append(f"evidence bundle unreadable: {bundle_error}")
    elif bundle.get("kind") != "github_validation_evidence_bundle":
        errors.append(f"unexpected evidence bundle kind: {bundle.get('kind')!r}")

    return errors, warnings, artifacts


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Patch Plan Full Validation", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Evidence bundle JSON: `{report['evidence_bundle']['json']}`")
    lines.append(f"- Evidence bundle Markdown: `{report['evidence_bundle']['markdown']}`")
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    for step in report.get("steps", []):
        lines.append(f"### {step['name']}")
        lines.append(f"- Return code: `{step['returncode']}`")
        lines.append(f"- OK: `{step['ok']}`")
        if step.get("error"):
            lines.append(f"- Error: `{step['error']}`")
        lines.append("")
    lines.append("## Artifact summary")
    lines.append("")
    for name, artifact in report.get("artifacts", {}).items():
        lines.append(f"- `{name}`: `{artifact}`")
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


def build_commands(args: argparse.Namespace, repo_root: Path) -> tuple[list[tuple[str, list[str], int]], Path, Path]:
    bundle_json, bundle_md = bundle_paths(repo_root, args.evidence_output_dir, args.bundle_basename)
    commands: list[tuple[str, list[str], int]] = [
        (
            "agent_review_patch_plan_smoke",
            [
                sys.executable,
                "Tools/validation/run_agent_review_patch_plan_smoke.py",
                "--repo-root",
                ".",
                "--orchestrator",
                args.orchestrator,
                "--evidence",
                args.evidence,
                "--min-patch-plans",
                str(args.min_patch_plans),
                "--tool-output",
                args.patch_plan,
                "--tool-markdown-output",
                args.patch_plan_markdown,
                "--output",
                args.smoke_output,
                "--markdown-output",
                args.smoke_markdown_output,
            ]
            + (["--expect-fallback"] if args.expect_fallback else []),
            args.timeout_seconds,
        ),
        (
            "docs_links",
            [
                sys.executable,
                "Tools/validation/check_docs_links.py",
                "--repo-root",
                ".",
                "--output",
                args.docs_links_output,
            ],
            args.timeout_seconds,
        ),
        (
            "python_syntax",
            [
                sys.executable,
                "Tools/validation/check_python_syntax.py",
                "--repo-root",
                ".",
                "--output",
                args.python_syntax_output,
            ],
            args.timeout_seconds,
        ),
        (
            "validation_report_contract",
            [
                sys.executable,
                "Tools/validation/check_validation_report_contract.py",
                "--repo-root",
                ".",
                "--output",
                args.validation_report_contract_output,
            ],
            args.timeout_seconds,
        ),
        (
            "build_github_evidence_bundle",
            [
                sys.executable,
                "Tools/ai/build_github_evidence_bundle.py",
                "--repo-root",
                ".",
                "--basename",
                args.bundle_basename,
                "--output-dir",
                args.evidence_output_dir,
                "--report",
                args.patch_plan,
                "--report",
                args.smoke_output,
                "--report",
                args.docs_links_output,
                "--report",
                args.python_syntax_output,
                "--report",
                args.validation_report_contract_output,
                "--selected-chunks-evidence",
                "__agent_review_patch_plan_no_selected_chunks__",
            ],
            args.timeout_seconds,
        ),
        (
            "check_github_evidence_bundle",
            [
                sys.executable,
                "Tools/validation/check_github_evidence_bundle.py",
                "--repo-root",
                ".",
                "--bundle",
                str(bundle_json),
                "--output",
                args.bundle_validation_output,
            ],
            args.timeout_seconds,
        ),
        (
            "git_diff_check",
            ["git", "diff", "--check"],
            args.git_timeout_seconds,
        ),
        (
            "git_status_short",
            ["git", "status", "--short"],
            args.git_timeout_seconds,
        ),
    ]
    return commands, bundle_json, bundle_md


def run_full_validation(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    commands, bundle_json, bundle_md = build_commands(args, repo_root)
    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for name, command, timeout_seconds in commands:
        result = run_command(command, repo_root, timeout_seconds)
        result["name"] = name
        steps.append(result)
        if not result["ok"] and name != "git_status_short":
            errors.append(f"{name} returned {result['returncode']}: {result.get('error') or result.get('stderr_tail') or result.get('stdout_tail')}")

    artifact_errors, artifact_warnings, artifacts = validate_expected_outputs(
        repo_root=repo_root,
        patch_plan_path=repo_path(repo_root, args.patch_plan),
        smoke_path=repo_path(repo_root, args.smoke_output),
        bundle_json=bundle_json,
        bundle_md=bundle_md,
        min_patch_plans=args.min_patch_plans,
        expect_fallback=args.expect_fallback,
    )
    errors.extend(artifact_errors)
    warnings.extend(artifact_warnings)

    return {
        "schema_version": 1,
        "kind": "agent_review_patch_plan_full_validation",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "evidence_writes_performed": True,
        "apply_mode": "report_only_full_validation_and_evidence_bundle",
        "steps": steps,
        "artifacts": artifacts,
        "evidence_bundle": {
            "json": rel(bundle_json, repo_root),
            "markdown": rel(bundle_md, repo_root),
            "validation_report": args.bundle_validation_output,
        },
        "decision": {
            "standard_validation_completed": not errors,
            "bundle_generated": bundle_json.exists() and bundle_md.exists(),
            "manual_review_required": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
        },
        "guardrails": {
            "report_only": True,
            "manual_review_required": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "blender_runtime_execution_performed": False,
            "npu_primary_advisory": False,
            "openvino_gpu_primary_lane": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--orchestrator", default=DEFAULT_ORCHESTRATOR)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--patch-plan", default=DEFAULT_PATCH_PLAN)
    parser.add_argument("--patch-plan-markdown", default=DEFAULT_PATCH_PLAN_MARKDOWN)
    parser.add_argument("--smoke-output", default=DEFAULT_SMOKE)
    parser.add_argument("--smoke-markdown-output", default=DEFAULT_SMOKE_MARKDOWN)
    parser.add_argument("--docs-links-output", default=DEFAULT_DOCS_LINKS)
    parser.add_argument("--python-syntax-output", default=DEFAULT_PYTHON_SYNTAX)
    parser.add_argument("--validation-report-contract-output", default=DEFAULT_REPORT_CONTRACT)
    parser.add_argument("--bundle-basename", default=DEFAULT_BUNDLE_BASENAME)
    parser.add_argument("--evidence-output-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--bundle-validation-output", default=DEFAULT_BUNDLE_VALIDATION)
    parser.add_argument("--min-patch-plans", type=int, default=12)
    parser.add_argument("--expect-fallback", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--git-timeout-seconds", type=int, default=60)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_full_validation(args)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

