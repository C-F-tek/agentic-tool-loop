#!/usr/bin/env python3
"""Analyze documentation contract drift for local AI/NPU workflow docs.

This validator is report-only. It checks whether central Markdown docs mention
important contracts introduced by the local AI core/tool lane and the workload
quality gate, then emits a concrete manual fix plan.

It does not rewrite Markdown, execute providers, apply patches, run Blender or
read ignored runtime outputs.
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


REPORT_KIND = "docs_contract_drift"

DOC_CHECKS: tuple[dict[str, Any], ...] = (
    {
        "path": "Tools/validation/README.md",
        "contract": "ai_workload_report_quality_validator_discoverability",
        "required_terms": (
            "check_ai_workload_report_quality.py",
            "ai_workload_report_quality",
            "usable_text_lanes_only_for_advisory_context",
            "npu_review_metadata",
        ),
        "recommended_terms": (
            "AI_WORKLOAD_REPORT_QUALITY_GATE.md",
            "metadata-only",
            "provider_execution_performed=false",
        ),
        "safe_patch_hint": "Add a focused section for the AI workload quality gate and link docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md.",
    },
    {
        "path": "docs/JSON_SCHEMAS.md",
        "contract": "ai_workload_report_quality_schema_contract",
        "required_terms": (
            "AI workload report quality",
            "ai_workload_report_quality",
            "npu_review_metadata",
            "usable_lanes",
            "unusable_lanes",
            "advisory_use",
        ),
        "recommended_terms": (
            "metadata_only",
            "generated_output_written",
            "quality_gate_required_before_advisory_use",
        ),
        "safe_patch_hint": "Add schema notes for ai_workload_report_quality and npu_review_metadata or link the dedicated contract doc.",
    },
    {
        "path": "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md",
        "contract": "core_activation_mentions_quality_gate",
        "required_terms": (
            "AI workload report quality gate",
            "check_ai_workload_report_quality.py",
            "Ollama/GPU",
            "NPU",
        ),
        "recommended_terms": (
            "usable_text",
            "unusable_output",
        ),
        "safe_patch_hint": "Reference the quality gate as the advisory context filter after provider/probe reports are generated.",
    },
    {
        "path": "docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md",
        "contract": "dedicated_quality_gate_contract",
        "required_terms": (
            "AI Workload Report Quality Gate",
            "check_ai_workload_report_quality.py",
            "ai_workload_report_quality",
            "npu_review_metadata",
            "provider_execution_performed=false",
            "OpenVINO/NPU",
            "Ollama/GPU/CUDA",
        ),
        "recommended_terms": (
            "quality_report_required_before_advisory_use",
            "fail closed",
        ),
        "safe_patch_hint": "Keep this document as the canonical contract and let large docs link to it instead of duplicating the full schema.",
    },
)

FORBIDDEN_TERMS = (
    "NPU as primary advisory",
    "OpenVINO GPU primary lane",
    "provider execution by default",
    "automatic patch apply is allowed",
)


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"


def check_doc(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    rel_path = str(spec["path"])
    text, error = read_text(repo_root / rel_path)
    required_terms = tuple(spec.get("required_terms") or ())
    recommended_terms = tuple(spec.get("recommended_terms") or ())
    missing_required = [term for term in required_terms if term not in text]
    missing_recommended = [term for term in recommended_terms if term not in text]
    forbidden_present = [term for term in FORBIDDEN_TERMS if term in text]

    errors: list[str] = []
    warnings: list[str] = []
    if error:
        errors.append(error)
    if missing_required:
        errors.extend(f"missing required term: {term}" for term in missing_required)
    if forbidden_present:
        errors.extend(f"forbidden term present: {term}" for term in forbidden_present)
    if missing_recommended:
        warnings.extend(f"missing recommended term: {term}" for term in missing_recommended)

    safe_actions: list[dict[str, str]] = []
    if missing_required or missing_recommended:
        safe_actions.append(
            {
                "path": rel_path,
                "operation": "manual_docs_patch_suggestion",
                "apply_mode": "manual_review_only",
                "hint": str(spec.get("safe_patch_hint") or "Add missing contract terms."),
            }
        )

    return {
        "path": rel_path,
        "contract": spec.get("contract"),
        "exists": (repo_root / rel_path).is_file(),
        "ok": not errors,
        "required_term_count": len(required_terms),
        "recommended_term_count": len(recommended_terms),
        "missing_required_terms": missing_required,
        "missing_recommended_terms": missing_recommended,
        "forbidden_terms_present": forbidden_present,
        "errors": errors,
        "warnings": warnings,
        "safe_actions": safe_actions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Docs Contract Drift Report", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Drift count: `{report['drift_count']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    for check in report["checks"]:
        lines.append(f"## `{check['path']}`")
        lines.append("")
        lines.append(f"- Contract: `{check['contract']}`")
        lines.append(f"- OK: `{check['ok']}`")
        if check["missing_required_terms"]:
            lines.append("- Missing required terms:")
            for term in check["missing_required_terms"]:
                lines.append(f"  - `{term}`")
        if check["missing_recommended_terms"]:
            lines.append("- Missing recommended terms:")
            for term in check["missing_recommended_terms"]:
                lines.append(f"  - `{term}`")
        if check["safe_actions"]:
            lines.append("- Suggested safe actions:")
            for action in check["safe_actions"]:
                lines.append(f"  - {action['hint']}")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("This report is advisory only. It does not rewrite Markdown or apply patches.")
    return "\n".join(lines) + "\n"


def validate_docs_contract_drift(repo_root: Path) -> dict[str, Any]:
    checks = [check_doc(repo_root, spec) for spec in DOC_CHECKS]
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
        if check.get("missing_required_terms") or check.get("missing_recommended_terms")
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
        "apply_mode": "report_only",
        "drift_count": drift_count,
        "checks": checks,
        "safe_actions": safe_actions,
        "guardrails": {
            "docs_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
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
    report = validate_docs_contract_drift(repo_root)

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
