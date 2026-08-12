#!/usr/bin/env python3
"""Build documentation follow-up suggestions from code patch plans.

This bridge lets the code patch-plan lane notify the documentation patch lane.
It reads an `agent_review_code_patch_plan` report and emits a report-only
`agent_review_code_docs_followup` artifact with documentation suggestions.

It does not apply code patches, edit documentation, execute providers, run
Blender or read ignored runtime output unless a report path is explicitly given.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    normalize_repo_path,
    now_iso,
    read_json_object,
    repo_rel,
    report_guardrail_errors,
    report_only_guardrails,
    resolve_output_path,
    write_json_and_markdown,
)


REPORT_KIND = "agent_review_code_docs_followup"
EXPECTED_CODE_PLAN_KIND = "agent_review_code_patch_plan"
DEFAULT_CODE_PATCH_PLAN = "output/patch_specs/agent_review_code_patch_plan.json"
DEFAULT_OUTPUT = "output/patch_specs/agent_review_code_docs_followup.json"
DEFAULT_MARKDOWN = "output/patch_specs/agent_review_code_docs_followup.md"

DOC_TARGETS_BY_AREA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("validation", ("Tools/validation/README.md", "docs/JSON_SCHEMAS.md", "docs/CONTRACT_DRIFT_VALIDATION.md")),
    ("cpu_validation", ("Tools/validation/README.md", "docs/JSON_SCHEMAS.md", "docs/CONTRACT_DRIFT_VALIDATION.md")),
    ("cpu_orchestration", ("docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md", "docs/LOCAL_AI_TASKS/README.md", "WORKFLOW.md")),
    ("workflow", ("docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md", "docs/LOCAL_AI_TASKS/README.md", "WORKFLOW.md")),
    ("ai", ("docs/AGENT_REVIEW_CODE_PATCH_PLAN.md", "docs/JSON_SCHEMAS.md", "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md")),
    ("npu", ("docs/LOCAL_AI_WORKFLOW.md", "docs/LOCAL_WORKSTATION_TARGET.md", "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md")),
)
DOC_TARGETS_BY_PATH_PREFIX: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tools/validation/", ("Tools/validation/README.md", "docs/JSON_SCHEMAS.md", "docs/CONTRACT_DRIFT_VALIDATION.md")),
    ("Tools/workflow/", ("docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md", "docs/LOCAL_AI_TASKS/README.md", "WORKFLOW.md")),
    ("Tools/ai/", ("docs/AGENT_REVIEW_CODE_PATCH_PLAN.md", "docs/JSON_SCHEMAS.md", "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md")),
    ("Tools/npu/", ("docs/LOCAL_AI_WORKFLOW.md", "docs/LOCAL_WORKSTATION_TARGET.md", "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md")),
    (".github/workflows/", ("docs/DEVELOPER_GUIDE.md", "docs/README.md", "WORKFLOW.md")),
)
FALLBACK_DOC_TARGETS = ("docs/AGENT_REVIEW_CODE_PATCH_PLAN.md", "docs/JSON_SCHEMAS.md")
DEFAULT_VALIDATION_COMMANDS = (
    "python .\\Tools\\validation\\check_docs_links.py --repo-root . --output .\\output\\validation\\docs_links.json",
    "python .\\Tools\\validation\\check_markdown_command_hygiene.py --repo-root . --output .\\output\\validation\\markdown_command_hygiene.json",
    "python .\\Tools\\validation\\check_validation_report_contract.py --repo-root . --output .\\output\\validation\\validation_report_contract.json",
    "git diff --check",
)


def existing_doc_targets(repo_root: Path, candidates: list[str]) -> tuple[list[str], list[str]]:
    """Split candidate docs into existing and missing repository files."""
    existing: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_repo_path(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if (repo_root / normalized).is_file():
            existing.append(normalized)
        else:
            missing.append(normalized)
    return existing, missing


def doc_candidates_for_plan(plan: dict[str, Any]) -> list[str]:
    """Map one code patch-plan item to candidate documentation surfaces."""
    candidates: list[str] = []
    area = str(plan.get("area") or "").lower()
    for key, docs in DOC_TARGETS_BY_AREA:
        if key in area:
            candidates.extend(docs)
    target_files = plan.get("target_files", [])
    if isinstance(target_files, list):
        for target in target_files:
            normalized = normalize_repo_path(target)
            for prefix, docs in DOC_TARGETS_BY_PATH_PREFIX:
                if normalized.startswith(prefix):
                    candidates.extend(docs)
    return unique_candidates(candidates or list(FALLBACK_DOC_TARGETS))


def unique_candidates(candidates: list[str]) -> list[str]:
    """Return normalized unique candidate paths in stable order."""
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_repo_path(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def normalized_target_files(plan: dict[str, Any]) -> list[str]:
    """Return normalized code target files from a patch plan."""
    target_files = plan.get("target_files", []) if isinstance(plan.get("target_files"), list) else []
    return [normalize_repo_path(target) for target in target_files]


def target_text_for_plan(plan: dict[str, Any]) -> str:
    """Return the rationale target text for one patch plan."""
    target_text = ", ".join(f"`{target}`" for target in normalized_target_files(plan))
    return target_text or "the code target"


def source_evidence_for_plan(plan: dict[str, Any], plan_id: str) -> dict[str, Any]:
    """Return the docs-follow-up source evidence block for one patch plan."""
    return {
        "code_patch_plan_id": plan_id,
        "code_target_files": normalized_target_files(plan),
        "code_rationale": plan.get("rationale"),
        "code_edit_strategy": plan.get("edit_strategy"),
    }


def docs_followup_for_plan(repo_root: Path, plan: dict[str, Any], index: int) -> dict[str, Any]:
    """Build one docs follow-up suggestion from one code patch-plan item."""
    plan_id = str(plan.get("id") or f"code_patch_{index:03d}")
    existing_targets, missing_targets = existing_doc_targets(repo_root, doc_candidates_for_plan(plan))
    return {
        "id": f"docs_followup_{index:03d}",
        "source_code_patch_plan_id": plan_id,
        "area": plan.get("area") or "docs_followup",
        "risk": "low" if plan.get("risk") in ("low", None) else "medium",
        "status": "candidate_for_manual_review",
        "target_files": existing_targets,
        "missing_candidate_docs": missing_targets,
        "rationale": f"Code patch plan `{plan_id}` may change {target_text_for_plan(plan)}; documentation should be reviewed for matching contract, workflow or schema updates.",
        "edit_strategy": "After the code patch is reviewed, update only the affected docs with a narrow cross-reference, schema note, validator command or workflow note. Do not duplicate full contracts and do not apply documentation edits automatically.",
        "validation_commands": list(DEFAULT_VALIDATION_COMMANDS),
        "stop_conditions": [
            "Stop if the related code patch is rejected or substantially changed.",
            "Stop if the docs update would touch output/**, generated indexes, full analysis JSON or runtime artifacts.",
            "Stop if documentation validation fails.",
        ],
        "manual_review_required": True,
        "source_evidence": source_evidence_for_plan(plan, plan_id),
    }


def validate_code_plan_report(code_plan: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """Validate the source code patch-plan report and return its plan list."""
    errors: list[str] = []
    if code_plan.get("kind") != EXPECTED_CODE_PLAN_KIND:
        errors.append(f"code patch plan kind must be {EXPECTED_CODE_PLAN_KIND}")
    errors.extend(report_guardrail_errors(code_plan, "code patch plan"))
    plans = code_plan.get("code_patch_plans", [])
    if not isinstance(plans, list):
        errors.append("code_patch_plans must be a list")
        return errors, []
    return errors, [plan for plan in plans if isinstance(plan, dict)]


def build_docs_followup(repo_root: Path, code_plan_path: Path) -> dict[str, Any]:
    """Build a report-only docs follow-up artifact from a code patch-plan report."""
    code_plan, load_errors = read_json_object(code_plan_path)
    errors = [f"code patch plan: {error}" for error in load_errors]
    warnings: list[str] = []
    suggestions: list[dict[str, Any]] = []

    if code_plan:
        validation_errors, plans = validate_code_plan_report(code_plan)
        errors.extend(validation_errors)
        suggestions = [docs_followup_for_plan(repo_root, plan, index) for index, plan in enumerate(plans, start=1)]
        if not suggestions:
            warnings.append("no docs follow-up suggestions were produced from the code patch plan")

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "apply_mode": "report_only_manual_review_docs_followup",
        "inputs": {
            "code_patch_plan": repo_rel(repo_root, code_plan_path),
            "code_patch_plan_kind": code_plan.get("kind") if code_plan else None,
            "code_patch_plan_count": code_plan.get("patch_plan_count") if code_plan else None,
        },
        "docs_followup_count": len(suggestions),
        "docs_followup_suggestions": suggestions,
        "decision": {
            "ready_for_manual_docs_review": bool(suggestions) and not errors,
            "docs_followup_count": len(suggestions),
            "manual_review_required": True,
            "recommended_next_layer": "review_docs_followups_after_code_plan" if suggestions and not errors else "no_docs_followup_ready",
        },
        "guardrails": report_only_guardrails(docs_written=False),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render docs follow-up suggestions as Markdown."""
    lines = ["# Agent Review Code Docs Follow-up", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Manual review required: `{report['manual_review_required']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append(f"- Docs follow-up count: `{report['docs_followup_count']}`")
    lines.append("")
    lines.append("## Suggestions")
    lines.append("")
    if not report.get("docs_followup_suggestions"):
        lines.append("- none")
    for suggestion in report.get("docs_followup_suggestions", []):
        lines.extend(render_suggestion(suggestion))
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This report notifies the documentation lane only. It is not a patch apply queue.")
    return "\n".join(lines) + "\n"


def render_suggestion(suggestion: dict[str, Any]) -> list[str]:
    """Render one docs follow-up suggestion."""
    lines = [f"### `{suggestion['id']}` from `{suggestion['source_code_patch_plan_id']}`", ""]
    lines.append(f"- Status: `{suggestion['status']}`")
    lines.append(f"- Target docs: `{', '.join(suggestion['target_files'])}`")
    if suggestion.get("missing_candidate_docs"):
        lines.append(f"- Missing candidate docs: `{', '.join(suggestion['missing_candidate_docs'])}`")
    lines.append(f"- Rationale: {suggestion['rationale']}")
    lines.append(f"- Strategy: {suggestion['edit_strategy']}")
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--code-patch-plan", default=DEFAULT_CODE_PATCH_PLAN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    code_plan_path = resolve_output_path(repo_root, args.code_patch_plan)
    report = build_docs_followup(repo_root, code_plan_path)
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
