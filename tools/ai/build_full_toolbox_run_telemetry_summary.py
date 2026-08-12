#!/usr/bin/env python3
"""Build a compact telemetry summary for full-toolbox decision-loop runs.

Report-only utility. It reads completed run reports and writes a compact JSON/MD
summary intended for docs/LOCAL_VALIDATION_EVIDENCE so GitHub/AI reviewers can
inspect run status, top recommendations, patch plans and performance telemetry
without committing output/**.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import now_iso, read_json_object, repo_rel
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import now_iso, read_json_object, repo_rel  # type: ignore
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_run_telemetry_summary.json"
DEFAULT_MARKDOWN = "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_run_telemetry_summary.md"


def read_optional_json(repo_root: Path, value: str) -> tuple[dict[str, Any], list[str], str]:
    if not value:
        return {}, [], ""
    path = resolve_output_path(repo_root, value)
    path_rel = repo_rel(repo_root, path)
    if not path.exists():
        return {}, [f"optional input missing: {path_rel}"], path_rel
    data, errors = read_json_object(path, missing_is_error=True)
    return data, errors, path_rel


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def provider_evidence_summary(orchestrator: dict[str, Any], gpu_report: dict[str, Any]) -> dict[str, Any]:
    gpu_round_count = safe_int(gpu_report.get("round_count"))
    gpu_provider_performed = bool(
        gpu_report.get("provider_execution_performed")
        and gpu_round_count > 0
        and str(gpu_report.get("classification") or "") != "required_provider_artifact_missing"
        and not bool(gpu_report.get("provider_empty_response"))
    )
    npu_audit_count = safe_int(orchestrator.get("npu_audit_count"))
    npu_success_count = safe_int(orchestrator.get("npu_audit_success_count"))
    npu_provider_performed = npu_success_count > 0
    degraded_reasons = []
    if isinstance(orchestrator.get("provider_degraded_reasons"), list):
        degraded_reasons.extend(str(item) for item in orchestrator.get("provider_degraded_reasons"))
    if not gpu_provider_performed and (orchestrator or gpu_report):
        degraded_reasons.append(
            "gpu_not_confirmed:"
            f"performed={gpu_report.get('provider_execution_performed')};"
            f"round_count={gpu_round_count};"
            f"classification={gpu_report.get('classification')};"
            f"passed={gpu_report.get('passed')}"
        )
    if orchestrator.get("npu_lane_mode") in {"skipped", "metadata_only", "degraded"} and npu_success_count == 0:
        degraded_reasons.append(
            "npu_auditor_not_confirmed:"
            f"audit_count={npu_audit_count};success_count={npu_success_count};"
            f"lane_mode={orchestrator.get('npu_lane_mode')}"
        )
    return {
        "provider_execution_requested": bool(orchestrator.get("provider_execution_performed") or gpu_report.get("provider_execution_requested")),
        "provider_execution_performed": bool(gpu_provider_performed or npu_provider_performed),
        "gpu_provider_execution_performed": gpu_provider_performed,
        "gpu_round_count": gpu_round_count,
        "gpu_returncode": orchestrator.get("gpu_returncode"),
        "gpu_classification": gpu_report.get("classification"),
        "gpu_provider_empty_response": bool(gpu_report.get("provider_empty_response")),
        "npu_provider_execution_performed": npu_provider_performed,
        "npu_audit_count": npu_audit_count,
        "npu_audit_success_count": npu_success_count,
        "npu_lane_mode": orchestrator.get("npu_lane_mode"),
        "provider_degraded_reasons": degraded_reasons,
    }


def compact_paths(values: Any, limit: int = 12) -> list[str]:
    out: list[str] = []
    for value in safe_list(values):
        text = str(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def compact_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    finding = safe_dict(item.get("repository_consistency_finding"))
    return {
        "id": item.get("id"),
        "area": item.get("area"),
        "risk": item.get("risk"),
        "status": item.get("status"),
        "target_files": compact_paths(item.get("target_files"), limit=6),
        "source": item.get("source"),
        "repository_consistency_kind": finding.get("kind"),
        "repository_consistency_severity": finding.get("severity"),
    }


def compact_patch_plan(item: dict[str, Any]) -> dict[str, Any]:
    source_evidence = safe_dict(item.get("source_evidence"))
    consistency = safe_dict(source_evidence.get("repository_consistency_finding"))
    return {
        "id": item.get("id"),
        "area": item.get("area"),
        "target_files": compact_paths(item.get("target_files"), limit=6),
        "manual_review_required": item.get("manual_review_required"),
        "cosmetic_patch_allowed": safe_dict(item.get("guardrails")).get("cosmetic_patch_allowed"),
        "repository_consistency_kind": consistency.get("kind"),
        "repository_consistency_severity": consistency.get("severity"),
    }


def compact_performance(data: dict[str, Any]) -> dict[str, Any]:
    performance = data.get("performance")
    return performance if isinstance(performance, dict) else {}


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    warnings: list[str] = []
    errors: list[str] = []

    decision_loop, decision_errors, decision_path = read_optional_json(repo_root, args.decision_loop)
    recommendations, recommendation_errors, recommendations_path = read_optional_json(repo_root, args.recommendations)
    patch_plan, patch_plan_errors, patch_plan_path = read_optional_json(repo_root, args.patch_plan)
    repository_map, repository_errors, repository_path = read_optional_json(repo_root, args.repository_consistency)
    repository_smoke, repository_smoke_errors, repository_smoke_path = read_optional_json(repo_root, args.repository_consistency_smoke)
    gpu_npu_sync, gpu_npu_errors, gpu_npu_path = read_optional_json(repo_root, args.gpu_npu_sync)
    orchestrator, orchestrator_errors, orchestrator_path = read_optional_json(repo_root, args.orchestrator)
    gpu_report, gpu_errors, gpu_path = read_optional_json(repo_root, args.gpu_report)

    hard_inputs = {
        "decision_loop": decision_loop,
        "recommendations": recommendations,
        "patch_plan": patch_plan,
    }
    errors.extend(decision_errors)
    errors.extend(recommendation_errors)
    errors.extend(patch_plan_errors)
    warnings.extend(repository_errors)
    warnings.extend(repository_smoke_errors)
    warnings.extend(gpu_npu_errors)
    warnings.extend(orchestrator_errors)
    warnings.extend(gpu_errors)

    for name, data in hard_inputs.items():
        if not data:
            errors.append(f"required telemetry input unavailable: {name}")

    recommendation_items = [item for item in safe_list(recommendations.get("recommendations")) if isinstance(item, dict)]
    patch_plan_items = [item for item in safe_list(patch_plan.get("patch_plans")) if isinstance(item, dict)]
    workflow_like = {
        "passed": decision_loop.get("passed"),
        "recommendation_count": decision_loop.get("recommendation_count") or recommendations.get("recommendation_count") or len(recommendation_items),
        "patch_plan_count": decision_loop.get("patch_plan_count") or patch_plan.get("patch_plan_count") or len(patch_plan_items),
        "deterministic_synthesizer_used": decision_loop.get("deterministic_synthesizer_used"),
        "patch_plan_fallback_used": decision_loop.get("patch_plan_fallback_used") or patch_plan.get("fallback_used"),
        "bundle_validation_passed": args.bundle_validation_passed,
        "evidence_to_commit": compact_paths(args.evidence_to_commit, limit=32),
    }

    provider_evidence = provider_evidence_summary(orchestrator, gpu_report)
    provider_execution = bool(provider_evidence["provider_execution_performed"])
    return {
        "schema_version": 1,
        "kind": "full_toolbox_run_telemetry_summary",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "stamp": args.stamp,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": provider_execution,
        "provider_evidence": provider_evidence,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "inputs": {
            "decision_loop": decision_path,
            "recommendations": recommendations_path,
            "patch_plan": patch_plan_path,
            "repository_consistency": repository_path,
            "repository_consistency_smoke": repository_smoke_path,
            "gpu_npu_sync": gpu_npu_path,
            "orchestrator": orchestrator_path,
            "gpu_report": gpu_path,
        },
        "run_parameters": {
            "budget_minutes": args.budget_minutes,
            "max_rounds": args.max_rounds,
            "files_per_round": args.files_per_round,
            "max_context_files": args.max_context_files,
            "max_chars_per_file": args.max_chars_per_file,
            "max_new_tokens": args.max_new_tokens,
            "npu_auditor_every_rounds": args.npu_auditor_every_rounds,
            "repository_consistency_map_workers": args.repository_consistency_map_workers,
        },
        "workflow_summary": workflow_like,
        "recommendations_first20": [compact_recommendation(item) for item in recommendation_items[:20]],
        "patch_plans_first20": [compact_patch_plan(item) for item in patch_plan_items[:20]],
        "repository_consistency": {
            "finding_count": repository_map.get("finding_count"),
            "severity_counts": repository_map.get("severity_counts"),
            "finding_kind_counts": repository_map.get("finding_kind_counts"),
            "performance": compact_performance(repository_map),
            "smoke_passed": repository_smoke.get("passed"),
            "smoke_mapper_report_reused": repository_smoke.get("mapper_report_reused"),
            "smoke_elapsed_seconds": repository_smoke.get("elapsed_seconds"),
        },
        "gpu_npu": {
            "provider_evidence": provider_evidence,
            "sync_metrics": gpu_npu_sync.get("metrics"),
            "performance": compact_performance(gpu_npu_sync),
            "operational_opinions": gpu_npu_sync.get("operational_opinions"),
            "refactoring_suggestions": gpu_npu_sync.get("refactoring_suggestions"),
        },
        "guardrails": {
            "report_only": True,
            "committable_location": "docs/LOCAL_VALIDATION_EVIDENCE",
            "raw_output_commit_allowed": False,
            "provider_execution_performed": provider_execution,
            "gpu_provider_execution_performed": provider_evidence.get("gpu_provider_execution_performed"),
            "npu_provider_execution_performed": provider_evidence.get("npu_provider_execution_performed"),
            "patch_application_performed": False,
            "source_writes_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Full Toolbox Run Telemetry Summary", ""]
    workflow = safe_dict(report.get("workflow_summary"))
    lines.append(f"- Passed: `{report.get('passed')}`")
    lines.append(f"- Stamp: `{report.get('stamp')}`")
    lines.append(f"- Recommendation count: `{workflow.get('recommendation_count')}`")
    lines.append(f"- Patch plan count: `{workflow.get('patch_plan_count')}`")
    lines.append(f"- Deterministic synthesizer used: `{workflow.get('deterministic_synthesizer_used')}`")
    lines.append(f"- Patch plan fallback used: `{workflow.get('patch_plan_fallback_used')}`")
    lines.append(f"- Provider execution performed: `{report.get('provider_execution_performed')}`")
    provider_evidence = safe_dict(report.get("provider_evidence"))
    lines.append(f"- GPU provider execution performed: `{provider_evidence.get('gpu_provider_execution_performed')}`")
    lines.append(f"- GPU round count: `{provider_evidence.get('gpu_round_count')}`")
    lines.append(f"- NPU provider execution performed: `{provider_evidence.get('npu_provider_execution_performed')}`")
    lines.append(f"- NPU audit success count: `{provider_evidence.get('npu_audit_success_count')}`")
    if provider_evidence.get("provider_degraded_reasons"):
        lines.append(f"- Provider degraded reasons: `{provider_evidence.get('provider_degraded_reasons')}`")
    lines.append("")
    lines.append("## Repository consistency performance")
    lines.append("")
    performance = safe_dict(safe_dict(report.get("repository_consistency")).get("performance"))
    for key in (
        "total_build_report_seconds",
        "markdown_scan_seconds",
        "file_discovery_seconds",
        "python_inventory_seconds",
        "path_index_seconds",
        "findings_build_seconds",
    ):
        lines.append(f"- `{key}`: `{performance.get(key)}`")
    lines.append("")
    lines.append("## Top recommendations")
    lines.append("")
    for item in safe_list(report.get("recommendations_first20")):
        lines.append(f"- `{item.get('id')}` `{item.get('area')}` `{item.get('risk')}` -> `{item.get('target_files')}`")
    lines.append("")
    lines.append("## Top patch plans")
    lines.append("")
    for item in safe_list(report.get("patch_plans_first20")):
        lines.append(f"- `{item.get('id')}` `{item.get('area')}` review=`{item.get('manual_review_required')}` -> `{item.get('target_files')}`")
    gpu_npu = safe_dict(report.get("gpu_npu"))
    if gpu_npu.get("operational_opinions"):
        lines.append("")
        lines.append("## GPU/NPU operational opinions")
        lines.append("")
        for item in safe_list(gpu_npu.get("operational_opinions")):
            lines.append(f"- {item}")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for item in safe_list(report.get("errors")):
            lines.append(f"- {item}")
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for item in safe_list(report.get("warnings"))[:30]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--decision-loop", required=True)
    parser.add_argument("--recommendations", required=True)
    parser.add_argument("--patch-plan", required=True)
    parser.add_argument("--repository-consistency", default="")
    parser.add_argument("--repository-consistency-smoke", default="")
    parser.add_argument("--gpu-npu-sync", default="")
    parser.add_argument("--orchestrator", default="")
    parser.add_argument("--gpu-report", default="")
    parser.add_argument("--evidence-to-commit", action="append", default=[])
    parser.add_argument("--bundle-validation-passed", action="store_true")
    parser.add_argument("--budget-minutes", type=int, default=0)
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--files-per-round", type=int, default=0)
    parser.add_argument("--max-context-files", type=int, default=0)
    parser.add_argument("--max-chars-per-file", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=0)
    parser.add_argument("--npu-auditor-every-rounds", type=int, default=0)
    parser.add_argument("--repository-consistency-map-workers", type=int, default=0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_summary(args)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end="")
    write_text_report(render_markdown(report) + "\n", markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
