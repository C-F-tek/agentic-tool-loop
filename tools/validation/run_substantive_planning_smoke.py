#!/usr/bin/env python3
"""Validate substantive-first recommendation and patch-plan reports.

Report-only smoke. It checks that deterministic recommendations and optional
patch plans are substantive, evidence-backed and not cosmetic-only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import normalize_repo_path, now_iso, read_json_object, repo_rel
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import normalize_repo_path, now_iso, read_json_object, repo_rel  # type: ignore
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "output/validation/substantive_planning_smoke.json"
DEFAULT_MARKDOWN = "output/validation/substantive_planning_smoke.md"
COSMETIC_KEYWORDS = (
    "whitespace",
    "space-only",
    "spacing-only",
    "tag spacing",
    "tag-spacing",
    "formatting-only",
    "cosmetic",
)
SUBSTANTIVE_AREAS = {
    "python_python",
    "md_python",
    "md_powershell",
    "md_md",
    "python_validation",
    "repository_consistency",
    "doc_code",
    "doc_doc",
}
FORBIDDEN_TARGET_PREFIXES = (
    "output/",
    "renders/",
    ".git/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
)


def read_json(path: Path) -> tuple[dict[str, Any], list[str]]:
    return read_json_object(path, missing_is_error=True)


def text_blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("id", "area", "rationale", "proposed_strategy", "edit_strategy")
    ).lower()


def is_cosmetic(item: dict[str, Any]) -> bool:
    return any(keyword in text_blob(item) for keyword in COSMETIC_KEYWORDS)


def target_errors(target_files: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(target_files, list) or not target_files:
        return ["target_files is empty or not a list"]
    for raw in target_files:
        path = normalize_repo_path(raw)
        if not path:
            errors.append("empty target path")
            continue
        if path.startswith(FORBIDDEN_TARGET_PREFIXES):
            errors.append(f"forbidden target prefix: {path}")
        if "*" in path or path.endswith("/"):
            errors.append(f"non-concrete target: {path}")
    return errors


def recommendation_has_consistency_evidence(item: dict[str, Any]) -> bool:
    if isinstance(item.get("repository_consistency_finding"), dict):
        return True
    evidence = item.get("source_evidence")
    return isinstance(evidence, dict) and isinstance(evidence.get("repository_consistency_finding"), dict)


def validate_recommendations(report: dict[str, Any], min_recommendations: int, min_substantive: int) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []
    substantive_count = 0
    consistency_count = 0
    cosmetic_count = 0

    if report.get("passed") is not True:
        errors.append("recommendation report did not pass")
    if len(recommendations) < min_recommendations:
        errors.append(f"recommendation_count {len(recommendations)} below minimum {min_recommendations}")

    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    declared_consistency = int(decision.get("substantive_consistency_recommendation_count") or 0)
    if declared_consistency < min_substantive:
        errors.append(f"substantive_consistency_recommendation_count {declared_consistency} below minimum {min_substantive}")

    for index, item in enumerate(recommendations, start=1):
        if not isinstance(item, dict):
            results.append({"index": index, "ok": False, "error": "recommendation is not an object"})
            continue
        item_errors = target_errors(item.get("target_files"))
        area = str(item.get("area") or "")
        has_consistency = recommendation_has_consistency_evidence(item)
        item_is_cosmetic = is_cosmetic(item)
        if area in SUBSTANTIVE_AREAS:
            substantive_count += 1
        if has_consistency:
            consistency_count += 1
        if item_is_cosmetic and not has_consistency:
            cosmetic_count += 1
            item_errors.append("cosmetic recommendation without repository consistency evidence")
        if not item.get("stop_conditions"):
            item_errors.append("missing stop_conditions")
        if not item.get("validation_commands"):
            item_errors.append("missing validation_commands")
        results.append(
            {
                "index": index,
                "id": item.get("id"),
                "area": area,
                "ok": not item_errors,
                "has_repository_consistency_evidence": has_consistency,
                "cosmetic": item_is_cosmetic,
                "errors": item_errors,
            }
        )
        errors.extend(f"recommendations[{index}] {error}" for error in item_errors)

    if substantive_count < min_recommendations:
        errors.append(f"substantive recommendation count {substantive_count} below minimum {min_recommendations}")
    if consistency_count < min_substantive:
        errors.append(f"repository consistency backed count {consistency_count} below minimum {min_substantive}")
    if cosmetic_count:
        errors.append(f"cosmetic recommendation count without evidence: {cosmetic_count}")
    if not errors and not recommendations:
        warnings.append("no recommendations were present, but no hard minimum was requested")
    return results, errors, warnings


def validate_patch_plan(report: dict[str, Any], min_patch_plans: int) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    if not report:
        return results, errors, warnings
    patch_plans = report.get("patch_plans") if isinstance(report.get("patch_plans"), list) else []
    if report.get("passed") is not True:
        errors.append("patch plan report did not pass")
    if len(patch_plans) < min_patch_plans:
        errors.append(f"patch_plan_count {len(patch_plans)} below minimum {min_patch_plans}")
    for index, item in enumerate(patch_plans, start=1):
        if not isinstance(item, dict):
            results.append({"index": index, "ok": False, "error": "patch plan is not an object"})
            continue
        item_errors = target_errors(item.get("target_files"))
        guardrails = item.get("guardrails") if isinstance(item.get("guardrails"), dict) else {}
        source_evidence = item.get("source_evidence") if isinstance(item.get("source_evidence"), dict) else {}
        if guardrails.get("cosmetic_patch_allowed") is not False:
            item_errors.append("guardrails.cosmetic_patch_allowed must be false")
        if is_cosmetic(item) and not isinstance(source_evidence.get("repository_consistency_finding"), dict):
            item_errors.append("cosmetic patch plan lacks repository consistency evidence")
        results.append(
            {
                "index": index,
                "id": item.get("id"),
                "area": item.get("area"),
                "ok": not item_errors,
                "errors": item_errors,
            }
        )
        errors.extend(f"patch_plans[{index}] {error}" for error in item_errors)
    if not patch_plans and min_patch_plans == 0:
        warnings.append("no patch plan was provided or required")
    return results, errors, warnings


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Substantive Planning Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Recommendation result count: `{len(report['recommendation_results'])}`")
    lines.append(f"- Patch plan result count: `{len(report['patch_plan_results'])}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("Smoke is report-only and validates substantive-first planning semantics.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--recommendations", required=True)
    parser.add_argument("--patch-plan", default="")
    parser.add_argument("--min-recommendations", type=int, default=1)
    parser.add_argument("--min-substantive", type=int, default=1)
    parser.add_argument("--min-patch-plans", type=int, default=0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    rec_path = resolve_output_path(repo_root, args.recommendations)
    patch_path = resolve_output_path(repo_root, args.patch_plan) if args.patch_plan else None
    recommendations, rec_errors = read_json(rec_path)
    patch_plan: dict[str, Any] = {}
    patch_errors: list[str] = []
    if patch_path:
        patch_plan, patch_errors = read_json(patch_path)

    rec_results, rec_validation_errors, rec_warnings = validate_recommendations(
        recommendations,
        args.min_recommendations,
        args.min_substantive,
    )
    patch_results, patch_validation_errors, patch_warnings = validate_patch_plan(patch_plan, args.min_patch_plans)
    errors = rec_errors + patch_errors + rec_validation_errors + patch_validation_errors
    warnings = rec_warnings + patch_warnings
    report = {
        "schema_version": 1,
        "kind": "substantive_planning_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "inputs": {
            "recommendations": repo_rel(repo_root, rec_path),
            "patch_plan": repo_rel(repo_root, patch_path) if patch_path else "",
        },
        "recommendation_results": rec_results,
        "patch_plan_results": patch_results,
        "guardrails": {
            "report_only": True,
            "cosmetic_patch_suppression_required": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
        },
    }
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    write_text_report(render_markdown(report), markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
