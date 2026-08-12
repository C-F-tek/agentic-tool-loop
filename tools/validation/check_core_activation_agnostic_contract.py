#!/usr/bin/env python3
"""Validate the local AI core activation agnostic contract.

This validator is intentionally static/report-only. It verifies that the core
activation workflow still wires the required layers:

- full-context pipeline orchestration;
- explicit-only multistep provider workflow;
- agnostic memory/tool/transient context artifacts;
- megalithic review consumption through report files;
- signal refinement and PR draft generation;
- no-apply/manual-review guardrails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

DEFAULT_WORKFLOW = "Tools/workflow/run_local_ai_core_tool_activation.ps1"
DEFAULT_OUTPUT = "output/validation/core_activation_agnostic_contract.json"
DEFAULT_MARKDOWN = "output/validation/core_activation_agnostic_contract.md"

REQUIRED_TERMS = {
    "pipeline_orchestration": [
        "run_local_ai_task_via_pipeline.ps1",
        "-FullContextGoldenPath",
        "-AgentStateObjective",
        "-BuildEvidence",
    ],
    "explicit_multistep_provider_workflow": [
        "-RunMultistepProviderWorkflow",
        "-RunOllamaProbe",
        "-RunNpuProbe",
        "-RunNpuDecodeSmoke",
        "-UsePrimaryAdvisoryProvider",
        "$UseExplicitProviders",
    ],
    "agnostic_context_artifacts": [
        "build_agent_memory_inventory.py",
        "build_agent_agnostic_tool_inventory.py",
        "build_agent_transient_request_context.py",
        "agent_memory_inventory_json",
        "agnostic_tool_inventory_json",
        "transient_request_context_json",
    ],
    "megalithic_review_stack": [
        "run_megalithic_repo_review.py",
        "--report-file",
        "$AgentMemoryInventoryJson",
        "$AgnosticToolInventoryJson",
        "$TransientRequestContextJson",
        "refine_megalithic_review_signals.py",
        "build_megalithic_review_pr_draft.py",
    ],
    "guardrails": [
        "provider_execution_policy",
        "explicit_only",
        "manual_review_only_no_auto_apply",
        "patch_application_performed",
        "blender_runtime_touched",
        "Provider execution explicit-only",
        "Patch application performed: False",
    ],
}

FORBIDDEN_TERMS = {
    "implicit_provider_execution": [
        "RunOllamaProbe = $true",
        "RunNpuProbe = $true",
        "UsePrimaryAdvisoryProvider = $true",
    ],
    "automatic_patch_application": [
        "apply_patch",
        "Invoke-Patch",
        "--apply",
        "Patch application performed: True",
    ],
}


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


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    workflow_path = repo_path(repo_root, args.workflow)
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    if not workflow_path.exists():
        errors.append(f"workflow missing: {rel(workflow_path, repo_root)}")
        text = ""
    else:
        text = workflow_path.read_text(encoding="utf-8-sig", errors="replace")

    for section, terms in REQUIRED_TERMS.items():
        missing = [term for term in terms if term not in text]
        ok = not missing
        checks.append(
            {
                "section": section,
                "ok": ok,
                "required_terms": terms,
                "missing_terms": missing,
            }
        )
        for term in missing:
            errors.append(f"{section}: missing required term: {term}")

    forbidden_hits: list[dict[str, str]] = []
    for section, terms in FORBIDDEN_TERMS.items():
        for term in terms:
            if term in text:
                forbidden_hits.append({"section": section, "term": term})
                errors.append(f"{section}: forbidden term present: {term}")

    return {
        "schema_version": 1,
        "kind": "core_activation_agnostic_contract",
        "repo_root": str(repo_root),
        "workflow": rel(workflow_path, repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_static_contract",
        "checks": checks,
        "forbidden_hits": forbidden_hits,
        "decision": {
            "pipeline_orchestration_present": not checks[0]["missing_terms"] if checks else False,
            "explicit_multistep_provider_workflow_present": not checks[1]["missing_terms"] if len(checks) > 1 else False,
            "agnostic_context_artifacts_present": not checks[2]["missing_terms"] if len(checks) > 2 else False,
            "megalithic_review_stack_present": not checks[3]["missing_terms"] if len(checks) > 3 else False,
            "guardrails_present": not checks[4]["missing_terms"] if len(checks) > 4 else False,
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "static_check_only": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Core Activation Agnostic Contract", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Workflow: `{report['workflow']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    for check in report["checks"]:
        lines.append(f"## {check['section']}")
        lines.append(f"- OK: `{check['ok']}`")
        if check["missing_terms"]:
            lines.append("- Missing:")
            for term in check["missing_terms"]:
                lines.append(f"  - `{term}`")
        lines.append("")
    if report["errors"]:
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
