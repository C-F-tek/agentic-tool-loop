#!/usr/bin/env python3
"""Build a conservative manual-review patch plan from GPU/NPU review artifacts.

This tool is intentionally report-only. It normalizes usable GPU planner
recommendations when they exist. If the GPU planner produced zero
recommendations while the evidence-sufficiency report contains ready candidates,
it builds a deterministic fallback plan from that evidence instead.

It never applies patches, never creates GitHub PRs, never writes SQLite, and
never promotes persistent memory.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report

DEFAULT_ORCHESTRATOR = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator_live.json"
DEFAULT_EVIDENCE = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_OUTPUT = "output/patch_specs/agent_review_patch_plan.json"
DEFAULT_MARKDOWN = "output/patch_specs/agent_review_patch_plan.md"

PLAN_KIND = "agent_review_patch_plan"
APPLY_MODE = "report_only_manual_review_patch_plan"

DEFAULT_VALIDATION_COMMANDS = [
    "python Tools/validation/check_python_syntax.py --repo-root . --output output/validation/python_syntax.json",
    "python Tools/validation/check_validation_report_contract.py --repo-root . --output output/validation/validation_report_contract.json",
    "git diff --check",
    "git status --short",
]

FORBIDDEN_TARGET_PREFIXES = (
    "output/",
    "renders/",
    ".git/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
)

FORBIDDEN_TARGET_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def load_json_object(path: Path) -> dict[str, Any]:
    data, errors = read_json_object(path)
    if errors:
        raise ValueError(f"{path}: {'; '.join(errors)}")
    return data




def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/")


def unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_repo_path(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def target_path_error(path_value: str, repo_root: Path) -> str | None:
    normalized = normalize_repo_path(path_value)
    if not normalized:
        return "empty target path"
    if Path(normalized).is_absolute():
        return "absolute target paths are not allowed"
    full = (repo_root / normalized).resolve()
    try:
        full.relative_to(repo_root.resolve())
    except ValueError:
        return "target path escapes repository root"
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        return f"forbidden generated/runtime target prefix: {normalized}"
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_TARGET_FRAGMENTS) and lower.endswith(".json"):
        return f"forbidden full-analysis JSON target: {normalized}"
    if "*" in normalized or normalized.endswith("/"):
        return "target is a glob or directory, not a concrete file"
    if not full.exists():
        return "target file does not exist"
    if not full.is_file():
        return "target is not a file"
    return None


def compact_evidence_files(item: dict[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for evidence_file in item.get("evidence_files", []) if isinstance(item.get("evidence_files"), list) else []:
        if not isinstance(evidence_file, dict):
            continue
        compact.append(
            {
                "path": evidence_file.get("path"),
                "exists": evidence_file.get("exists"),
                "kind": evidence_file.get("kind"),
                "matched_terms": evidence_file.get("matched_terms", []),
            }
        )
    return compact


COSMETIC_PATCH_KEYWORDS = (
    "whitespace",
    "space-only",
    "spacing-only",
    "tag spacing",
    "tag-spacing",
    "formatting-only",
    "cosmetic",
)


def recommendation_text_blob(rec: dict[str, Any]) -> str:
    return " ".join(
        str(rec.get(key) or "")
        for key in ("area", "rationale", "proposed_strategy", "edit_strategy")
    ).lower()


def has_substantive_consistency_evidence(rec: dict[str, Any]) -> bool:
    if isinstance(rec.get("repository_consistency_finding"), dict):
        return True
    evidence = rec.get("source_evidence")
    return isinstance(evidence, dict) and isinstance(evidence.get("repository_consistency_finding"), dict)


def is_cosmetic_recommendation(rec: dict[str, Any]) -> bool:
    if has_substantive_consistency_evidence(rec):
        return False
    text = recommendation_text_blob(rec)
    return any(keyword in text for keyword in COSMETIC_PATCH_KEYWORDS)

def load_gpu_report(repo_root: Path, orchestrator: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    gpu_output = orchestrator.get("gpu_output")
    if not gpu_output:
        return {}
    path = resolve_path(repo_root, str(gpu_output))
    if not path.exists():
        warnings.append(f"GPU report referenced by orchestrator is missing: {repo_rel(path, repo_root)}")
        return {}
    try:
        return load_json_object(path)
    except Exception as exc:  # noqa: BLE001 - report-only diagnostic.
        warnings.append(f"Unable to read GPU report {repo_rel(path, repo_root)}: {type(exc).__name__}: {exc}")
        return {}


def npu_audit_refs(orchestrator: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for audit in orchestrator.get("npu_audits", []) if isinstance(orchestrator.get("npu_audits"), list) else []:
        if not isinstance(audit, dict):
            continue
        refs.append(
            {
                "round": audit.get("round"),
                "status": audit.get("status"),
                "classification": audit.get("classification"),
                "provider_execution_requested": audit.get("provider_execution_requested"),
                "provider_load_attempted": audit.get("provider_load_attempted"),
                "provider_execution_succeeded": audit.get("provider_execution_succeeded"),
                "provider_execution_performed": audit.get("provider_execution_performed"),
                "dependency_missing": audit.get("dependency_missing"),
                "gpu_review_blocked": audit.get("gpu_review_blocked"),
                "audit_output": audit.get("audit_output"),
            }
        )
    return refs


def normalize_gpu_recommendation(
    *,
    rec: dict[str, Any],
    index: int,
    repo_root: Path,
    audit_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if is_cosmetic_recommendation(rec):
        return None, {"id": str(rec.get("id") or f"gpu_{index:03d}"), "reason": "cosmetic/formatting-only recommendation suppressed"}
    target_files = unique_strings(rec.get("target_files", []) if isinstance(rec.get("target_files"), list) else [])
    if not target_files:
        return None, {"id": str(rec.get("id") or f"gpu_{index:03d}"), "reason": "GPU recommendation has no concrete target_files"}
    errors = [f"{path}: {target_path_error(path, repo_root)}" for path in target_files if target_path_error(path, repo_root)]
    if errors:
        return None, {"id": str(rec.get("id") or f"gpu_{index:03d}"), "reason": "; ".join(errors)}
    return (
        {
            "id": str(rec.get("id") or f"gpu_{index:03d}"),
            "source": "gpu_recommendation",
            "area": rec.get("area") or "other",
            "status": "ready_for_manual_review",
            "target_files": target_files,
            "rationale": rec.get("rationale") or "GPU planner recommendation normalized for manual-review patch planning.",
            "edit_strategy": rec.get("proposed_strategy") or "Apply only a small, reviewable patch supported by the cited evidence.",
            "risk": rec.get("risk") or "medium",
            "validation_commands": rec.get("validation_commands") or DEFAULT_VALIDATION_COMMANDS,
            "stop_conditions": rec.get("stop_conditions")
            or [
                "Stop if target files changed since the review artifact was generated.",
                "Stop if the edit requires running Blender runtime or provider execution.",
                "Stop if the patch touches generated output, full analysis JSON, SQLite, or semantic indexes.",
            ],
            "source_evidence": {
                "gpu_recommendation": rec,
                "repository_consistency_finding": rec.get("repository_consistency_finding"),
                "npu_audit_refs": audit_refs,
            },
            "manual_review_required": True,
            "guardrails": {
                "cosmetic_patch_allowed": False,
                "manual_review_required": True,
                "patch_application_performed": False,
            },
        },
        None,
    )


def plan_from_doc_code_item(
    *,
    item: dict[str, Any],
    index: int,
    repo_root: Path,
    audit_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    doc = normalize_repo_path(item.get("doc"))
    if not doc:
        return None, {"id": f"fallback_doc_code_{index:03d}", "reason": "doc_code item has no source doc"}
    error = target_path_error(doc, repo_root)
    if error:
        return None, {"id": f"fallback_doc_code_{index:03d}", "reason": f"{doc}: {error}"}
    reference = normalize_repo_path(item.get("reference"))
    existing_candidate = normalize_repo_path(item.get("existing_candidate"))
    candidates = unique_strings(item.get("candidate_references", []) if isinstance(item.get("candidate_references"), list) else [])
    strategy_bits = [
        "Patch the source Markdown only; do not create missing code/runtime files from this fallback.",
        f"Review the referenced path `{reference}` and decide whether it is stale, intentionally future-facing, or should point to an existing artifact.",
    ]
    if existing_candidate:
        strategy_bits.append(f"Existing candidate `{existing_candidate}` was detected; prefer link normalization over new content.")
    if candidates:
        strategy_bits.append(f"Candidate references observed: {', '.join(f'`{candidate}`' for candidate in candidates[:8])}.")
    return (
        {
            "id": f"fallback_doc_code_{index:03d}",
            "source": "evidence_sufficiency_fallback",
            "area": "doc_code",
            "status": "ready_for_manual_review",
            "target_files": [doc],
            "rationale": item.get("reason") or "Evidence report marks this doc/code reference as sufficient for manual patch planning.",
            "edit_strategy": " ".join(strategy_bits),
            "risk": "low",
            "validation_commands": DEFAULT_VALIDATION_COMMANDS,
            "stop_conditions": [
                "Stop if the reference actually exists after refreshing the branch.",
                "Stop if the fix requires creating runtime code instead of correcting documentation.",
                "Stop if the edit would touch output/**, generated indexes, full analysis JSON, or Blender runtime behavior.",
            ],
            "source_evidence": {
                "evidence_area": "doc_code",
                "reference": reference,
                "candidate_references": candidates,
                "existing_candidate": existing_candidate or None,
                "confidence": item.get("confidence"),
                "evidence_files": compact_evidence_files(item),
                "npu_audit_refs": audit_refs,
            },
            "manual_review_required": True,
        },
        None,
    )


def plan_from_doc_doc_item(
    *,
    item: dict[str, Any],
    index: int,
    repo_root: Path,
    audit_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    path = normalize_repo_path(item.get("path"))
    if not path:
        return None, {"id": f"fallback_doc_doc_{index:03d}", "reason": "doc_doc item has no target path"}
    error = target_path_error(path, repo_root)
    if error:
        return None, {"id": f"fallback_doc_doc_{index:03d}", "reason": f"{path}: {error}"}
    missing_terms = [str(term) for term in item.get("missing_terms", []) if str(term).strip()] if isinstance(item.get("missing_terms"), list) else []
    terms_text = ", ".join(f"`{term}`" for term in missing_terms[:12]) or "the missing explicit terms"
    return (
        {
            "id": f"fallback_doc_doc_{index:03d}",
            "source": "evidence_sufficiency_fallback",
            "area": "doc_doc",
            "status": "ready_for_manual_review",
            "target_files": [path],
            "rationale": item.get("reason") or "Evidence report marks this documentation cross-reference as sufficient.",
            "edit_strategy": (
                f"Add a small targeted cross-reference for {terms_text}. "
                "Do not duplicate large contract sections; link or summarize the canonical location instead."
            ),
            "risk": "low",
            "validation_commands": DEFAULT_VALIDATION_COMMANDS,
            "stop_conditions": [
                "Stop if the missing terms are already present after refreshing the branch.",
                "Stop if the change duplicates entire contract documents instead of adding a narrow cross-reference.",
                "Stop if the edit would touch generated output or runtime files.",
            ],
            "source_evidence": {
                "evidence_area": "doc_doc",
                "missing_terms": missing_terms,
                "confidence": item.get("confidence"),
                "evidence_files": compact_evidence_files(item),
                "npu_audit_refs": audit_refs,
            },
            "manual_review_required": True,
        },
        None,
    )


def fallback_plans_from_evidence(
    *,
    evidence: dict[str, Any],
    repo_root: Path,
    audit_refs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    plans: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    areas = evidence.get("areas", {}) if isinstance(evidence.get("areas"), dict) else {}

    doc_code = areas.get("doc_code", {}) if isinstance(areas.get("doc_code"), dict) else {}
    for index, item in enumerate(doc_code.get("items", []) if isinstance(doc_code.get("items"), list) else [], start=1):
        if not isinstance(item, dict) or not item.get("evidence_sufficient"):
            continue
        plan, skip = plan_from_doc_code_item(item=item, index=index, repo_root=repo_root, audit_refs=audit_refs)
        if plan:
            plans.append(plan)
        if skip:
            skipped.append(skip)

    doc_doc = areas.get("doc_doc", {}) if isinstance(areas.get("doc_doc"), dict) else {}
    for index, item in enumerate(doc_doc.get("items", []) if isinstance(doc_doc.get("items"), list) else [], start=1):
        if not isinstance(item, dict) or not item.get("evidence_sufficient"):
            continue
        plan, skip = plan_from_doc_doc_item(item=item, index=index, repo_root=repo_root, audit_refs=audit_refs)
        if plan:
            plans.append(plan)
        if skip:
            skipped.append(skip)

    return plans, skipped


def gpu_plans_from_report(
    *,
    gpu_report: dict[str, Any],
    repo_root: Path,
    audit_refs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    plans: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    recommendations = gpu_report.get("recommendations", [])
    if not isinstance(recommendations, list):
        return plans, [{"id": "gpu_report", "reason": "GPU report recommendations is not a list"}]
    for index, rec in enumerate(recommendations, start=1):
        if not isinstance(rec, dict):
            skipped.append({"id": f"gpu_{index:03d}", "reason": "recommendation is not an object"})
            continue
        if rec.get("status") != "ready_for_patch_plan":
            continue
        plan, skip = normalize_gpu_recommendation(rec=rec, index=index, repo_root=repo_root, audit_refs=audit_refs)
        if plan:
            plans.append(plan)
        if skip:
            skipped.append(skip)
    return plans, skipped


def build_decision(
    *,
    plans: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    gpu_report: dict[str, Any],
    evidence: dict[str, Any],
    fallback_used: bool,
) -> dict[str, Any]:
    evidence_decision = evidence.get("decision", {}) if isinstance(evidence.get("decision"), dict) else {}
    gpu_decision = gpu_report.get("decision", {}) if isinstance(gpu_report.get("decision"), dict) else {}
    return {
        "ready_for_manual_review": bool(plans),
        "patch_plan_count": len(plans),
        "skipped_candidate_count": len(skipped),
        "gpu_recommendation_count": gpu_report.get("recommendation_count", 0),
        "gpu_ready_count": gpu_decision.get("ready_count", 0),
        "fallback_used": fallback_used,
        "evidence_ready_for_manual_patch_count": evidence_decision.get("ready_for_manual_patch_count"),
        "evidence_sufficient_for_real_pr": evidence_decision.get("sufficient_for_real_pr"),
        "recommended_next_layer": "manual_review_then_targeted_patch" if plans else "collect_more_evidence",
        "manual_review_required": True,
        "cosmetic_patch_suppression_enabled": True,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Patch Plan", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Patch plan count: `{report['decision']['patch_plan_count']}`")
    lines.append(f"- Fallback used: `{report['decision']['fallback_used']}`")
    lines.append(f"- Manual review required: `{report['decision']['manual_review_required']}`")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    for key, value in report.get("inputs", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Patch plans")
    lines.append("")
    if not report.get("patch_plans"):
        lines.append("- none")
    for plan in report.get("patch_plans", []):
        lines.append(f"### {plan.get('id')} — {plan.get('area')}")
        lines.append(f"- Source: `{plan.get('source')}`")
        lines.append(f"- Risk: `{plan.get('risk')}`")
        lines.append(f"- Target files: `{plan.get('target_files')}`")
        lines.append(f"- Rationale: {plan.get('rationale')}")
        lines.append(f"- Strategy: {plan.get('edit_strategy')}")
        lines.append("")
    if report.get("skipped_candidates"):
        lines.append("## Skipped candidates")
        lines.append("")
        for item in report["skipped_candidates"]:
            lines.append(f"- `{item.get('id')}`: {item.get('reason')}")
        lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This artifact is a plan only. It contains no replacements and must not be treated as an apply queue.")
    return "\n".join(lines) + "\n"


def build_patch_plan(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    warnings: list[str] = []
    errors: list[str] = []

    orchestrator_path = resolve_path(repo_root, args.orchestrator)
    evidence_path = resolve_path(repo_root, args.evidence)
    orchestrator: dict[str, Any] = {}
    evidence: dict[str, Any] = {}

    if orchestrator_path.exists():
        try:
            orchestrator = load_json_object(orchestrator_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Unable to read orchestrator report: {type(exc).__name__}: {exc}")
    else:
        warnings.append(f"orchestrator report missing: {repo_rel(orchestrator_path, repo_root)}")

    if evidence_path.exists():
        try:
            evidence = load_json_object(evidence_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Unable to read evidence report: {type(exc).__name__}: {exc}")
    else:
        errors.append(f"evidence report missing: {repo_rel(evidence_path, repo_root)}")

    audit_refs = npu_audit_refs(orchestrator)
    gpu_report = load_gpu_report(repo_root, orchestrator, warnings) if orchestrator else {}
    plans, skipped = gpu_plans_from_report(gpu_report=gpu_report, repo_root=repo_root, audit_refs=audit_refs) if gpu_report else ([], [])

    fallback_used = False
    if not plans and evidence:
        fallback_used = True
        fallback_plans, fallback_skipped = fallback_plans_from_evidence(
            evidence=evidence,
            repo_root=repo_root,
            audit_refs=audit_refs,
        )
        plans.extend(fallback_plans)
        skipped.extend(fallback_skipped)

    if not plans and not errors:
        warnings.append("no patch plans were produced from GPU recommendations or evidence fallback")

    available_patch_plan_count = len(plans)
    requested_max_patch_plans = int(getattr(args, "max_patch_plans", 0) or 0)
    max_patch_plans = 0
    if requested_max_patch_plans > 0:
        warnings.append(
            "max_patch_plans is accepted for compatibility/telemetry but does not truncate patch plans; "
            "patch_plan_count may be lower than available_patch_plan_count only through guardrail rejection"
        )

    decision = build_decision(
        plans=plans,
        skipped=skipped,
        gpu_report=gpu_report,
        evidence=evidence,
        fallback_used=fallback_used,
    )
    return {
        "schema_version": 1,
        "kind": PLAN_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": APPLY_MODE,
        "inputs": {
            "orchestrator": repo_rel(orchestrator_path, repo_root),
            "evidence": repo_rel(evidence_path, repo_root),
            "gpu_report": orchestrator.get("gpu_output"),
            "orchestrator_kind": orchestrator.get("kind"),
            "evidence_kind": evidence.get("kind"),
            "gpu_kind": gpu_report.get("kind"),
        },
        "decision": decision,
        "patch_plan_count": len(plans),
        "available_patch_plan_count": available_patch_plan_count,
        "max_patch_plans": max_patch_plans,
        "requested_max_patch_plans": requested_max_patch_plans,
        "patch_plans": plans,
        "skipped_candidate_count": len(skipped),
        "skipped_candidates": skipped,
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
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-patch-plans", type=int, default=0, help="Compatibility/telemetry only; does not truncate valid patch plans.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_patch_plan(args)
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
                "patch_plan_count": report["patch_plan_count"],
                "available_patch_plan_count": report.get("available_patch_plan_count"),
                "max_patch_plans": report.get("max_patch_plans"),
                "requested_max_patch_plans": report.get("requested_max_patch_plans"),
                "fallback_used": report["decision"]["fallback_used"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "manual_review_required": report["decision"]["manual_review_required"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
