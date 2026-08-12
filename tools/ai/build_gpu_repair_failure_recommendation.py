#!/usr/bin/env python3
"""Build a report-only recommendation for GPU planner repair failures.

This tool converts a known empty-recommendation failure mode into an explicit,
manual-review diagnostic artifact. It does not run providers, apply patches,
write source files, execute Blender, write SQLite databases or change Git state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "gpu_repair_failure_recommendation"
REPAIR_FAILURE_REASON = "repair_attempt_failed"


def now_iso() -> str:
    """Return a local ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    """Resolve a user-supplied path against the repository root."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(repo_root: Path, path: Path) -> str:
    """Return a repository-relative path when possible."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def read_json_object(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Read a JSON object or return errors."""
    if not path.exists():
        return {}, [f"missing file: {path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {}, [f"invalid JSON in {path}: {type(exc).__name__}: {exc}"]
    except OSError as exc:
        return {}, [f"cannot read {path}: {type(exc).__name__}: {exc}"]
    if not isinstance(value, dict):
        return {}, [f"JSON root must be an object: {path}"]
    return value, []


def int_field(data: dict[str, Any], *names: str) -> int:
    """Return the first integer-like field from the supplied names."""
    for name in names:
        value = data.get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def str_field(data: dict[str, Any], *names: str) -> str:
    """Return the first non-empty string field from the supplied names."""
    for name in names:
        value = data.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


def nested_dict(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a nested dict field if present."""
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def gpu_summary(orchestrator: dict[str, Any], gpu_report: dict[str, Any]) -> dict[str, Any]:
    """Collect GPU failure metadata from orchestrator and GPU report shapes."""
    decision = nested_dict(orchestrator, "decision")
    gpu_decision = nested_dict(gpu_report, "decision")
    gpu_summary_data = nested_dict(orchestrator, "gpu_summary")
    return {
        "gpu_recommendation_count": int_field(gpu_report, "recommendation_count", "filtered_recommendation_count")
        or int_field(orchestrator, "gpu_recommendation_count"),
        "raw_recommendation_candidate_count": int_field(gpu_report, "raw_recommendation_candidate_count"),
        "filtered_recommendation_count": int_field(gpu_report, "filtered_recommendation_count"),
        "json_parse_error_count": int_field(gpu_report, "json_parse_error_count"),
        "repair_attempt_count": int_field(gpu_report, "repair_attempt_count"),
        "empty_recommendations_reason": str_field(gpu_report, "empty_recommendations_reason")
        or str_field(gpu_summary_data, "empty_recommendations_reason")
        or str_field(orchestrator, "gpu_empty_recommendations_reason")
        or str_field(decision, "gpu_empty_recommendations_reason"),
        "evidence_ready_for_manual_patch_count": int_field(gpu_report, "evidence_ready_for_manual_patch_count")
        or int_field(orchestrator, "gpu_evidence_ready_for_manual_patch_count")
        or int_field(gpu_summary_data, "evidence_ready_for_manual_patch_count"),
        "recommended_next_layer": str_field(gpu_report, "recommended_next_layer")
        or str_field(gpu_decision, "recommended_next_layer")
        or str_field(decision, "recommended_next_layer"),
        "provider_execution_performed": bool(
            orchestrator.get("provider_execution_performed") or gpu_report.get("provider_execution_performed")
        ),
        "patch_application_performed": bool(
            orchestrator.get("patch_application_performed") or gpu_report.get("patch_application_performed")
        ),
        "source_writes_performed": bool(orchestrator.get("source_writes_performed") or gpu_report.get("source_writes_performed")),
    }


def should_emit_recommendation(summary: dict[str, Any]) -> bool:
    """Return true when the repair failure should become an explicit recommendation."""
    return (
        summary["empty_recommendations_reason"] == REPAIR_FAILURE_REASON
        and summary["gpu_recommendation_count"] == 0
        and summary["evidence_ready_for_manual_patch_count"] > 0
    )


def build_recommendation(summary: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic diagnostic recommendation."""
    return {
        "id": "gpu_repair_failure_001",
        "area": "provider_orchestration",
        "status": "ready_for_manual_review",
        "risk": "medium",
        "target_files": [
            "Tools/ai/run_agent_gpu_deep_planning_review.py",
            "Tools/ai/run_agent_gpu_deep_planning_supervised.py",
            "Tools/ai/run_agent_gpu_npu_parallel_orchestrator.py",
            "docs/LOCAL_AI_TASKS/gpu-npu-parallel-evidence-runbook.md",
        ],
        "rationale": (
            "GPU/Ollama provider execution completed but produced zero usable recommendations because "
            f"`{REPAIR_FAILURE_REASON}` was reported while {summary['evidence_ready_for_manual_patch_count']} "
            "manual-review evidence candidates were ready."
        ),
        "proposed_strategy": (
            "Make the repair-failure path explicit in reports and review flow: preserve parse diagnostics, "
            "surface fallback plan readiness, and route reviewers to the deterministic manual-review patch-plan layer "
            "instead of leaving the result as an unexplained empty recommendation set."
        ),
        "validation_commands": [
            "python -m py_compile .\\Tools\\ai\\run_agent_gpu_deep_planning_review.py .\\Tools\\ai\\run_agent_gpu_deep_planning_supervised.py .\\Tools\\ai\\run_agent_gpu_npu_parallel_orchestrator.py",
            "python .\\Tools\\validation\\run_agent_review_patch_plan_smoke.py --repo-root . --orchestrator .\\output\\ai_pipeline\\project_complete_<STAMP>_orchestrator.json --evidence .\\output\\ai_pipeline\\agent_review_evidence_sufficiency.json --output .\\output\\validation\\agent_review_patch_plan_smoke_project_complete_<STAMP>.json --markdown-output .\\output\\validation\\agent_review_patch_plan_smoke_project_complete_<STAMP>.md",
            "python -m Tools.validation.check_github_evidence_bundle --repo-root . --bundle .\\docs\\LOCAL_VALIDATION_EVIDENCE\\project_complete_ai_to_ai_bundle_<STAMP>.json --output .\\output\\validation\\project_complete_ai_to_ai_bundle_<STAMP>_validation.json",
            "git diff --check",
        ],
        "stop_conditions": [
            "Stop if the fix would force the GPU planner to invent repository patch recommendations.",
            "Stop if the fix requires automatic patch application.",
            "Stop if the fix requires Blender runtime execution.",
            "Stop if raw output/** reports would be committed instead of compact evidence.",
        ],
        "static_provider_agreement": "provider_failure_mode_detected_with_static_evidence_ready",
        "manual_review_required": True,
    }


def build_report(repo_root: Path, orchestrator_path: Path, gpu_report_path: Path) -> dict[str, Any]:
    """Build the report-only diagnostic recommendation artifact."""
    orchestrator, orchestrator_errors = read_json_object(orchestrator_path)
    gpu_report, gpu_errors = read_json_object(gpu_report_path)
    errors = [*orchestrator_errors, *gpu_errors]
    summary = gpu_summary(orchestrator, gpu_report) if not errors else {}
    recommendations = [build_recommendation(summary)] if summary and should_emit_recommendation(summary) else []
    warnings: list[str] = []
    if summary and summary.get("empty_recommendations_reason") != REPAIR_FAILURE_REASON:
        warnings.append("GPU empty recommendation reason is not repair_attempt_failed")
    if summary and summary.get("gpu_recommendation_count", 0) > 0:
        warnings.append("GPU report already contains recommendations; diagnostic fallback not emitted")
    if summary and summary.get("evidence_ready_for_manual_patch_count", 0) <= 0:
        warnings.append("No ready manual-review evidence candidates were detected")
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
        "apply_mode": "report_only_gpu_repair_failure_recommendation",
        "inputs": {
            "orchestrator": repo_rel(repo_root, orchestrator_path),
            "gpu_report": repo_rel(repo_root, gpu_report_path),
        },
        "gpu_failure_summary": summary,
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "decision": {
            "repair_failure_recommendation_emitted": bool(recommendations),
            "recommended_next_layer": "build_agent_review_patch_plan.py"
            if recommendations
            else summary.get("recommended_next_layer", "") if summary else "",
            "manual_review_required": True,
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "blender_runtime_execution_performed": False,
            "sqlite_write_performed": False,
            "manual_review_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the diagnostic recommendation as Markdown."""
    lines = ["# GPU Repair Failure Recommendation", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Recommendation count: `{report['recommendation_count']}`")
    lines.append(f"- Manual review required: `{report['manual_review_required']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    lines.append("## GPU failure summary")
    lines.append("")
    for key, value in report.get("gpu_failure_summary", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    if not report.get("recommendations"):
        lines.append("- none")
    for rec in report.get("recommendations", []):
        lines.append(f"### `{rec['id']}` — {rec['area']}")
        lines.append("")
        lines.append(f"- Status: `{rec['status']}`")
        lines.append(f"- Risk: `{rec['risk']}`")
        lines.append(f"- Target files: `{', '.join(rec['target_files'])}`")
        lines.append(f"- Rationale: {rec['rationale']}")
        lines.append(f"- Strategy: {rec['proposed_strategy']}")
        lines.append(f"- Static/provider agreement: `{rec['static_provider_agreement']}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--orchestrator", required=True)
    parser.add_argument("--gpu-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root, resolve_path(repo_root, args.orchestrator), resolve_path(repo_root, args.gpu_report))
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "recommendation_count": report["recommendation_count"],
                "repair_failure_recommendation_emitted": report["decision"]["repair_failure_recommendation_emitted"],
                "patch_application_performed": report["patch_application_performed"],
                "source_writes_performed": report["source_writes_performed"],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
