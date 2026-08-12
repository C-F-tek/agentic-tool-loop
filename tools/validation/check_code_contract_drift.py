#!/usr/bin/env python3
"""Analyze code contract drift for IA-Carmine local AI tooling.

This validator is report-only. It checks that important Python/PowerShell tools
still expose the symbols and guardrail strings required by the local AI core/tool
lane, workload quality gate, docs drift tooling and macro-patch workflow.

It does not execute providers, apply patches, run Blender, read ignored runtime
outputs, modify source files or inspect SQLite memory databases.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


REPORT_KIND = "code_contract_drift"


@dataclass(frozen=True)
class CodeContractSpec:
    path: str
    contract: str
    owner_lane: str
    consumed_by_lanes: tuple[str, ...]
    required_terms: tuple[str, ...]
    recommended_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allowed_global_forbidden_terms: tuple[str, ...] = ()
    safe_patch_hint: str = "Add the missing contract term or update the contract spec if the implementation intentionally moved."


CODE_CONTRACTS: tuple[CodeContractSpec, ...] = (
    CodeContractSpec(
        path="Tools/workflow/run_local_ai_core_tool_activation.ps1",
        contract="local_ai_core_tool_activation_guardrails",
        owner_lane="cpu_orchestration",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "UseExplicitProviders",
            "GenerateMacroPatchDrafts",
            "provider_execution_policy",
            "manual_review_only_no_auto_apply",
            "patch_application_performed",
            "FullContextGoldenPath",
            "BuildEvidence",
        ),
        recommended_terms=(
            "local_ai_core_tool_activation_summary",
            "NPU knowledge-broker",
            "macro patch",
        ),
        forbidden_terms=("git merge", "git push --force"),
        safe_patch_hint="Keep activation provider-free by default and preserve explicit-only provider and manual-review macro-patch flags.",
    ),
    CodeContractSpec(
        path="Tools/validation/check_ai_workload_report_quality.py",
        contract="ai_workload_quality_gate_report_contract",
        owner_lane="cpu_validation",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "ai_workload_report_quality",
            "usable_text_lanes_only_for_advisory_context",
            "provider_execution_performed",
            "source_writes_performed",
            "advisory_use",
            "quality_decision",
            "openvino_npu",
            "gpu_cuda",
        ),
        recommended_terms=("npu_excluded_from_primary_advisory", "ollama_gpu_primary_advisory_allowed"),
        safe_patch_hint="Restore explicit decision metadata and lane role mapping before this validator is used by packet/proposal builders.",
    ),
    CodeContractSpec(
        path="Tools/ai/workload_quality.py",
        contract="workload_quality_fail_closed_routing",
        owner_lane="cpu_validation",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "TRACKED_WORKLOAD_PATH_SUFFIXES",
            "tracked_workload_lane_for_path",
            "is_tracked_workload_path",
            "quality_report_missing_fail_closed",
            "route_context_files_by_quality",
            "trusted_context_file_paths",
            "quality_routing_fail_closed_for_tracked_workload_reports",
        ),
        recommended_terms=("advisory_lanes", "excluded_advisory_lanes"),
        safe_patch_hint="Ensure known workload reports fail closed when the quality report is missing or unreadable.",
    ),
    CodeContractSpec(
        path="Tools/ai/suggest_repository_updates.py",
        contract="packet_builder_quality_approved_context_only",
        owner_lane="cpu_packet_builder",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "TRACKED_WORKLOAD_CONTEXT_FILES",
            "build_advisory_context_routing",
            "routing_unavailable_fail_closed_for_tracked_workload_reports",
            "quality-approved-workload-context-only",
            "provider_execution_performed",
            "excluded_context_files",
        ),
        recommended_terms=("Use only quality-approved AI workload context files", "advisory_context_routing"),
        safe_patch_hint="Keep workload report content filtered by quality routing before it is read into packets.",
    ),
    CodeContractSpec(
        path="Tools/ai/build_repository_change_proposals.py",
        contract="repository_proposals_quality_gate_evidence",
        owner_lane="cpu_proposal_builder",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "P-AI-WORKLOAD-REPORT-QUALITY-GATE",
            "workload_quality_decision",
            "evidence_summary",
            "manual_review_only",
            "provider_execution_performed",
            "suggestion_outputs",
        ),
        recommended_terms=("npu_excluded_from_primary_advisory", "ollama_gpu_primary_advisory_allowed"),
        safe_patch_hint="Keep proposal evidence tied to the workload quality report decision and keep proposals manual-review-only.",
    ),
    CodeContractSpec(
        path="Tools/npu/run_npu_review.py",
        contract="npu_review_metadata_sidecar",
        owner_lane="npu_explicit_provider_tool",
        consumed_by_lanes=("cpu", "npu"),
        required_terms=(
            "metadata-only",
            "metadata_out",
            "npu_review_metadata",
            "provider_execution_performed",
            "generated_output_written",
            "quality_gate_required_before_advisory_use",
            "patch_application_performed",
        ),
        recommended_terms=("provider not loaded", "probe_or_knowledge_broker"),
        safe_patch_hint="Keep metadata-only available so validation can inspect advisory role without importing OpenVINO or loading providers.",
    ),
    CodeContractSpec(
        path="Tools/validation/check_docs_contract_drift.py",
        contract="docs_contract_drift_report_only",
        owner_lane="cpu_validation",
        consumed_by_lanes=("cpu", "gpu_cuda", "npu"),
        required_terms=(
            "docs_contract_drift",
            "patch_application_performed",
            "provider_execution_performed",
            "manual_docs_patch_suggestion",
            "safe_actions",
            "openvino_gpu_primary_lane",
        ),
        recommended_terms=("AI_WORKLOAD_REPORT_QUALITY_GATE.md", "quality_report_required_before_advisory_use"),
        allowed_global_forbidden_terms=(
            "OpenVINO GPU primary lane",
            "provider execution by default",
        ),
        safe_patch_hint="Keep docs drift as report-only analysis that emits safe manual actions.",
    ),
    CodeContractSpec(
        path="Tools/validation/apply_docs_contract_drift_fixes.py",
        contract="docs_contract_drift_explicit_fixer",
        owner_lane="cpu_validation_explicit_docs_fixer",
        consumed_by_lanes=("cpu",),
        required_terms=(
            "--apply",
            "dry_run_report_only",
            "explicit_docs_only",
            "docs_only",
            "provider_execution_performed",
            "patch_application_performed",
            "source_writes_performed",
        ),
        recommended_terms=("idempotent", "AI workload report quality gate"),
        forbidden_terms=("subprocess.run", "os.system"),
        safe_patch_hint="Keep docs fixer idempotent, docs-only and gated by explicit --apply.",
    ),
)

FORBIDDEN_GLOBAL_TERMS: tuple[str, ...] = (
    "OpenVINO GPU primary lane",
    "provider execution by default",
    "auto-apply patches by default",
)

LANE_POLICY = {
    "cpu": "validators, contract analyzers, packet/proposal builders and orchestration run here by default",
    "gpu_cuda": "Ollama/GPU may produce advisory workload reports only through explicit provider commands",
    "npu": "OpenVINO/NPU may produce probe/knowledge-broker metadata or workload reports only through explicit provider commands",
}


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"


def check_contract(repo_root: Path, spec: CodeContractSpec) -> dict[str, Any]:
    path = repo_root / spec.path
    text, read_error = read_text(path)
    missing_required = [term for term in spec.required_terms if term not in text]
    missing_recommended = [term for term in spec.recommended_terms if term not in text]
    forbidden_present = [term for term in spec.forbidden_terms if term in text]
    forbidden_global_present = [
        term
        for term in FORBIDDEN_GLOBAL_TERMS
        if term in text and term not in spec.allowed_global_forbidden_terms
    ]
    allowed_global_forbidden_present = [
        term
        for term in spec.allowed_global_forbidden_terms
        if term in text
    ]

    errors: list[str] = []
    warnings: list[str] = []
    if read_error:
        errors.append(read_error)
    if missing_required:
        errors.extend(f"missing required term: {term}" for term in missing_required)
    if forbidden_present:
        errors.extend(f"forbidden term present: {term}" for term in forbidden_present)
    if forbidden_global_present:
        errors.extend(f"forbidden global term present: {term}" for term in forbidden_global_present)
    if missing_recommended:
        warnings.extend(f"missing recommended term: {term}" for term in missing_recommended)

    safe_actions: list[dict[str, str]] = []
    if missing_required or missing_recommended or forbidden_present or forbidden_global_present:
        safe_actions.append(
            {
                "path": spec.path,
                "operation": "manual_code_patch_suggestion",
                "apply_mode": "manual_review_only",
                "owner_lane": spec.owner_lane,
                "hint": spec.safe_patch_hint,
            }
        )

    return {
        "path": spec.path,
        "contract": spec.contract,
        "owner_lane": spec.owner_lane,
        "consumed_by_lanes": list(spec.consumed_by_lanes),
        "exists": path.is_file(),
        "ok": not errors,
        "required_term_count": len(spec.required_terms),
        "recommended_term_count": len(spec.recommended_terms),
        "missing_required_terms": missing_required,
        "missing_recommended_terms": missing_recommended,
        "forbidden_terms_present": forbidden_present,
        "forbidden_global_terms_present": forbidden_global_present,
        "allowed_global_forbidden_terms_present": allowed_global_forbidden_present,
        "errors": errors,
        "warnings": warnings,
        "safe_actions": safe_actions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Code Contract Drift Report", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Drift count: `{report['drift_count']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    lines.append("## Lane policy")
    lines.append("")
    for lane, description in report["lane_policy"].items():
        lines.append(f"- `{lane}`: {description}")
    lines.append("")
    for check in report["checks"]:
        lines.append(f"## `{check['path']}`")
        lines.append("")
        lines.append(f"- Contract: `{check['contract']}`")
        lines.append(f"- Owner lane: `{check['owner_lane']}`")
        lines.append(f"- Consumed by lanes: `{', '.join(check['consumed_by_lanes'])}`")
        lines.append(f"- OK: `{check['ok']}`")
        if check["missing_required_terms"]:
            lines.append("- Missing required terms:")
            for term in check["missing_required_terms"]:
                lines.append(f"  - `{term}`")
        if check["missing_recommended_terms"]:
            lines.append("- Missing recommended terms:")
            for term in check["missing_recommended_terms"]:
                lines.append(f"  - `{term}`")
        if check["forbidden_terms_present"] or check["forbidden_global_terms_present"]:
            lines.append("- Forbidden terms present:")
            for term in check["forbidden_terms_present"] + check["forbidden_global_terms_present"]:
                lines.append(f"  - `{term}`")
        if check.get("allowed_global_forbidden_terms_present"):
            lines.append("- Allowed guardrail literals present:")
            for term in check["allowed_global_forbidden_terms_present"]:
                lines.append(f"  - `{term}`")
        if check["safe_actions"]:
            lines.append("- Suggested safe actions:")
            for action in check["safe_actions"]:
                lines.append(f"  - {action['hint']}")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("This validator is report-only. Code changes remain manual-review-only and must be promoted through normal PRs.")
    return "\n".join(lines) + "\n"


def validate_code_contract_drift(repo_root: Path) -> dict[str, Any]:
    checks = [check_contract(repo_root, spec) for spec in CODE_CONTRACTS]
    errors = [
        f"{check['path']}: {error}"
        for check in checks
        for error in check.get("errors", [])
    ]
    warnings = [
        f"{check['path']}: {warning}"
        for check in checks
        for warning in check.get("warnings", [])
    ]
    safe_actions = [
        action
        for check in checks
        for action in check.get("safe_actions", [])
    ]
    drift_count = sum(
        1
        for check in checks
        if check.get("missing_required_terms")
        or check.get("missing_recommended_terms")
        or check.get("forbidden_terms_present")
        or check.get("forbidden_global_terms_present")
    )

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_manual_review_only",
        "drift_count": drift_count,
        "lane_policy": LANE_POLICY,
        "checks": checks,
        "safe_actions": safe_actions,
        "guardrails": {
            "code_report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "full_analysis_json_touched": False,
            "sqlite_db_touched": False,
            "npu_promoted_to_advisory": False,
            "openvino_gpu_primary_lane": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--markdown-output", help="Optional Markdown report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = validate_code_contract_drift(repo_root)

    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")

    if args.markdown_output:
        markdown_output = resolve_output_path(repo_root, args.markdown_output)
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")

    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
