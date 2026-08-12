#!/usr/bin/env python3
"""Run the report-only agent review decision loop.

This wrapper closes the local AI review loop without reimplementing either
decision layer:

1. build deterministic schema-valid recommendations from evidence/GPU/tool reports;
2. write a bridge orchestrator for the existing patch-plan builder;
3. build the existing manual-review patch plan.

It is report-only: no providers, no patch application, no SQLite writes, no
Blender runtime and no GitHub actions are executed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.build_agent_review_patch_plan import build_patch_plan, render_markdown as render_patch_plan_markdown
    from Tools.ai.build_deterministic_recommendations import (
        build_patch_plan_bridge_orchestrator,
        build_recommendation_report,
        load_report_at,
        render_markdown as render_recommendations_markdown,
        resolve_path,
    )
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.build_agent_review_patch_plan import build_patch_plan, render_markdown as render_patch_plan_markdown  # type: ignore
    from Tools.ai.build_deterministic_recommendations import (  # type: ignore
        build_patch_plan_bridge_orchestrator,
        build_recommendation_report,
        load_report_at,
        render_markdown as render_recommendations_markdown,
        resolve_path,
    )
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore

DEFAULT_EVIDENCE = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_ORCHESTRATOR = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator_live.json"
DEFAULT_RECOMMENDATIONS_OUTPUT = "output/ai_pipeline/agent_review_decision_loop_deterministic_recommendations.json"
DEFAULT_RECOMMENDATIONS_MARKDOWN = "output/ai_pipeline/agent_review_decision_loop_deterministic_recommendations.md"
DEFAULT_BRIDGE_ORCHESTRATOR = "output/ai_pipeline/agent_review_decision_loop_bridge_orchestrator.json"
DEFAULT_PATCH_PLAN_OUTPUT = "output/patch_specs/agent_review_patch_plan.json"
DEFAULT_PATCH_PLAN_MARKDOWN = "output/patch_specs/agent_review_patch_plan.md"
DEFAULT_OUTPUT = "output/ai_pipeline/agent_review_decision_loop.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_review_decision_loop.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def compact_output_result(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": repo_rel(path, repo_root),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def build_patch_plan_from_bridge_args(
    *,
    repo_root: Path,
    bridge_orchestrator: Path,
    evidence_path: Path,
    patch_plan_output: Path,
    patch_plan_markdown: Path,
    max_patch_plans: int = 0,
) -> dict[str, Any]:
    args = argparse.Namespace(
        repo_root=str(repo_root),
        orchestrator=str(bridge_orchestrator),
        evidence=str(evidence_path),
        output=str(patch_plan_output),
        markdown_output=str(patch_plan_markdown),
        max_patch_plans=max_patch_plans,
    )
    return build_patch_plan(args)


def build_decision_loop_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    evidence_path = resolve_path(repo_root, args.evidence)
    source_orchestrator_path = resolve_path(repo_root, args.orchestrator)
    recommendations_output = resolve_path(repo_root, args.recommendations_output)
    recommendations_markdown = resolve_path(repo_root, args.recommendations_markdown)
    bridge_orchestrator_output = resolve_path(repo_root, args.bridge_orchestrator_output)
    patch_plan_output = resolve_path(repo_root, args.patch_plan_output)
    patch_plan_markdown = resolve_path(repo_root, args.patch_plan_markdown)

    recommendation_args = argparse.Namespace(
        repo_root=str(repo_root),
        evidence=str(evidence_path),
        orchestrator=str(source_orchestrator_path),
        gpu_report=args.gpu_report,
        tool_report=list(args.tool_report or []),
        max_recommendations=args.max_recommendations,
    )
    recommendation_report = build_recommendation_report(recommendation_args)
    if recommendation_report.get("errors"):
        errors.extend(f"recommendations: {error}" for error in recommendation_report["errors"])
    warnings.extend(f"recommendations: {warning}" for warning in recommendation_report.get("warnings", []))

    write_json_report(recommendation_report, recommendations_output)
    write_text_report(render_recommendations_markdown(recommendation_report), recommendations_markdown)

    source_orchestrator, source_orchestrator_warnings = load_report_at(
        repo_root,
        source_orchestrator_path,
        missing_is_error=False,
    )
    warnings.extend(f"source_orchestrator: {warning}" for warning in source_orchestrator_warnings)

    bridge_report = build_patch_plan_bridge_orchestrator(
        repo_root=repo_root,
        recommendation_report=recommendation_report,
        recommendation_output=recommendations_output,
        source_orchestrator=source_orchestrator,
    )
    write_json_report(bridge_report, bridge_orchestrator_output)

    patch_plan_report: dict[str, Any] = {}
    if recommendation_report.get("passed") is True and recommendation_report.get("recommendation_count", 0) > 0:
        patch_plan_report = build_patch_plan_from_bridge_args(
            repo_root=repo_root,
            bridge_orchestrator=bridge_orchestrator_output,
            evidence_path=evidence_path,
            patch_plan_output=patch_plan_output,
            patch_plan_markdown=patch_plan_markdown,
            max_patch_plans=int(args.max_patch_plans),
        )
        if patch_plan_report.get("errors"):
            errors.extend(f"patch_plan: {error}" for error in patch_plan_report["errors"])
        warnings.extend(f"patch_plan: {warning}" for warning in patch_plan_report.get("warnings", []))
        write_json_report(patch_plan_report, patch_plan_output)
        write_text_report(render_patch_plan_markdown(patch_plan_report), patch_plan_markdown)
    else:
        errors.append("recommendation stage did not produce schema-valid recommendations for patch-plan build")

    recommendation_count = int(recommendation_report.get("recommendation_count") or 0)
    patch_plan_count = int(patch_plan_report.get("patch_plan_count") or 0) if patch_plan_report else 0
    if recommendation_count < int(args.min_recommendations):
        errors.append(
            f"recommendation_count below minimum: expected >= {args.min_recommendations}, got {recommendation_count}"
        )
    if patch_plan_count < int(args.min_patch_plans):
        errors.append(f"patch_plan_count below minimum: expected >= {args.min_patch_plans}, got {patch_plan_count}")

    if patch_plan_report and patch_plan_report.get("decision", {}).get("fallback_used") is True:
        warnings.append("patch_plan fallback_used=true; deterministic bridge was bypassed or produced no usable GPU recommendations")

    return {
        "schema_version": 1,
        "kind": "agent_review_decision_loop",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "recommendation_count": recommendation_count,
        "patch_plan_count": patch_plan_count,
        "deterministic_synthesizer_used": recommendation_report.get("decision", {}).get(
            "deterministic_synthesizer_used"
        ),
        "patch_plan_fallback_used": patch_plan_report.get("decision", {}).get("fallback_used") if patch_plan_report else None,
        "next_best_action": "manual_review_patch_plan" if patch_plan_count else "collect_more_evidence",
        "outputs": {
            "recommendations": compact_output_result(recommendations_output, repo_root),
            "recommendations_markdown": compact_output_result(recommendations_markdown, repo_root),
            "bridge_orchestrator": compact_output_result(bridge_orchestrator_output, repo_root),
            "patch_plan": compact_output_result(patch_plan_output, repo_root),
            "patch_plan_markdown": compact_output_result(patch_plan_markdown, repo_root),
        },
        "inputs": {
            "evidence": repo_rel(evidence_path, repo_root),
            "orchestrator": repo_rel(source_orchestrator_path, repo_root),
            "gpu_report": args.gpu_report,
            "tool_report_count": len(args.tool_report or []),
            "max_recommendations": args.max_recommendations,
            "max_patch_plans": args.max_patch_plans,
            "recommendation_kind": recommendation_report.get("kind"),
            "patch_plan_kind": patch_plan_report.get("kind") if patch_plan_report else None,
        },
        "decision": {
            "recommendations_ready": recommendation_count >= int(args.min_recommendations),
            "patch_plan_ready": patch_plan_count >= int(args.min_patch_plans),
            "manual_review_required": True,
            "recommended_next_layer": "manual_review_patch_plan" if patch_plan_count else "collect_more_evidence",
        },
        "guardrails": {
            "report_only": True,
            "manual_review_required": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "blender_runtime_execution_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "real_github_pr_created": False,
            "npu_primary_advisory": False,
            "openvino_gpu_primary_lane": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Decision Loop", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Recommendation count: `{report['recommendation_count']}`")
    lines.append(f"- Patch plan count: `{report['patch_plan_count']}`")
    lines.append(f"- Deterministic synthesizer used: `{report.get('deterministic_synthesizer_used')}`")
    lines.append(f"- Patch plan fallback used: `{report.get('patch_plan_fallback_used')}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for key, value in report.get("outputs", {}).items():
        lines.append(
            f"- `{key}`: `{value.get('path')}` exists=`{value.get('exists')}` size=`{value.get('size_bytes')}`"
        )
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
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("Report-only decision loop. No provider execution, patch application, SQLite write or Blender runtime.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--orchestrator", default=DEFAULT_ORCHESTRATOR)
    parser.add_argument("--gpu-report", default="")
    parser.add_argument("--tool-report", action="append", default=[])
    parser.add_argument("--max-recommendations", type=int, default=20)
    parser.add_argument("--max-patch-plans", type=int, default=0, help="Maximum patch plans to keep; 0 means no additional cap.")
    parser.add_argument("--min-recommendations", type=int, default=1)
    parser.add_argument("--min-patch-plans", type=int, default=1)
    parser.add_argument("--recommendations-output", default=DEFAULT_RECOMMENDATIONS_OUTPUT)
    parser.add_argument("--recommendations-markdown", default=DEFAULT_RECOMMENDATIONS_MARKDOWN)
    parser.add_argument("--bridge-orchestrator-output", default=DEFAULT_BRIDGE_ORCHESTRATOR)
    parser.add_argument("--patch-plan-output", default=DEFAULT_PATCH_PLAN_OUTPUT)
    parser.add_argument("--patch-plan-markdown", default=DEFAULT_PATCH_PLAN_MARKDOWN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_decision_loop_report(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "recommendation_count": report["recommendation_count"],
                "patch_plan_count": report["patch_plan_count"],
                "deterministic_synthesizer_used": report["deterministic_synthesizer_used"],
                "patch_plan_fallback_used": report["patch_plan_fallback_used"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
