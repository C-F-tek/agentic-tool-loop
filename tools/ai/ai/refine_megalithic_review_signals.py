#!/usr/bin/env python3
"""Refine noisy findings from a megalithic repository review.

The all-resources review intentionally casts a wide net. This post-pass keeps
that broad coverage but separates actionable discrepancies from expected
guardrails, normalized path aliases, placeholders, generated/legacy duplicates
and generic utility-symbol noise.

It is report-only and never applies patches or creates GitHub PRs.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_REVIEW = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_repo_review.json"
DEFAULT_PROPOSALS = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_repo_review_proposals.json"
DEFAULT_OUTPUT = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review.json"
DEFAULT_PROPOSALS_OUTPUT = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_proposals.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review.md"

KNOWN_TOP_LEVELS = {
    ".github",
    "docs",
    "Tools",
    "Scripting",
    "patch_specs",
    "EXECUTION_PLANS",
    "old script legacy",
    "indexAI",
    "output",
}
KNOWN_ROOT_FILES = {"AGENTS.md", "WORKFLOW.md", "CONTRIBUTING.md", "README.md"}
LOW_SIGNAL_DOCS = {".aider.chat.history.md"}
BACKUP_OR_GENERATED_SEGMENTS = {
    "old script legacy",
    "v61b_backgood",
    "indexAI",
    "generated_blender_script_candidate.py",
    "generated_blender_script_candidate_FristNear.py",
}
PLACEHOLDER_PATH_REFERENCES = {
    "Scripting/package_name",
    "Tools/validation/fixtures",
    "patch_specs/inbox",
    "Tools/npu/npu_preflight_report.json",
}
GENERATED_REFERENCE_PREFIXES = (
    "output/",
    "indexAI/",
)
PATH_ALIAS_PREFIXES = (
    ("EXECUTION_PLANS/", "docs/EXECUTION_PLANS/"),
    ("github/workflows/", ".github/workflows/"),
    (".github/workflows/", ".github/workflows/"),
)
ALLOW_DUPLICATE_SYMBOLS = {
    "__init__",
    "main",
    "execute",
    "draw",
    "add",
    "add_error",
    "add_item",
    "append_output",
    "apply_filter",
    "artifact_extra_roots",
    "ask_bool",
    "build_inventory",
    "build_layout",
    "build_ollama_prompt",
    "build_packet",
    "build_plan",
    "build_proposals",
    "build_report",
    "build_steps",
    "check_policy",
    "classify_path",
    "cleanup_intermediates",
    "cleanup_render_frames",
    "compact",
    "compact_text",
    "configure_headings",
    "copy_selected_path",
    "dry_run_spec",
    "ensure_repo_imports",
    "extract_symbols",
    "file_meta",
    "file_record",
    "format_symbol_summary",
    "from_mapping",
    "Get-RepoRelativePath",
    "Invoke-Step",
    "Resolve-ExistingPath",
    "Resolve-RepoRoot",
    "Write-Step",
}
CONCEPTUAL_SLASH_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def repo_root_from_review(review: dict[str, Any]) -> Path:
    raw = review.get("repo_root") or "."
    return Path(str(raw)).resolve()


def normalize_reference(reference: str) -> str:
    return reference.strip().strip("`.,:)];\"").replace("\\", "/").lstrip("/")


def candidate_references(reference: str) -> list[str]:
    ref = normalize_reference(reference)
    candidates = [ref]
    if ref in KNOWN_ROOT_FILES:
        candidates.append(ref)
    for prefix, replacement in PATH_ALIAS_PREFIXES:
        if ref.startswith(prefix):
            candidates.append(replacement + ref[len(prefix):])
    if ref.startswith("docs/") is False and ref.startswith("EXECUTION_PLANS/"):
        candidates.append("docs/" + ref)
    return list(dict.fromkeys(item for item in candidates if item))


def existing_candidate(reference: str, repo_root: Path) -> str | None:
    for candidate in candidate_references(reference):
        path = repo_root / candidate
        if path.exists():
            return candidate
    return None


def has_path_intent(reference: str) -> bool:
    ref = normalize_reference(reference)
    if not ref or ref.startswith(("http://", "https://")):
        return False
    if ref in KNOWN_ROOT_FILES:
        return True
    first = ref.split("/", 1)[0]
    if first in KNOWN_TOP_LEVELS:
        return True
    suffix = Path(ref).suffix.lower()
    return suffix in {".py", ".ps1", ".sh", ".md", ".json", ".yaml", ".yml", ".txt"}


def is_conceptual_slash_term(reference: str) -> bool:
    ref = normalize_reference(reference)
    if has_path_intent(ref):
        return False
    if "." in ref and "/" not in ref:
        return False
    return bool(CONCEPTUAL_SLASH_RE.match(ref))


def is_placeholder_reference(reference: str) -> bool:
    ref = normalize_reference(reference)
    return ref in PLACEHOLDER_PATH_REFERENCES or any(ref.startswith(prefix) for prefix in GENERATED_REFERENCE_PREFIXES)


def classify_ai_workload_failure(report: dict[str, Any]) -> dict[str, Any]:
    errors = report.get("errors") or []
    npu_only = bool(errors) and all(str(item).lower().startswith("npu:") for item in errors)
    if report.get("kind") == "ai_workload_report_quality" and npu_only:
        return {
            "classification": "expected_guardrail",
            "severity": "info",
            "area": "advisory_quality_gate",
            "title": "NPU report excluded by AI workload quality gate",
            "details": [
                "The ai_workload_report_quality report failed because the NPU workload text is unusable.",
                "This is expected fail-closed behavior when Ollama/GPU remains the usable advisory lane.",
                *[str(item) for item in errors],
            ],
        }
    return {
        "classification": "actionable_failure",
        "severity": "high",
        "area": "validation_reports",
        "title": "Validation report failure requires review",
        "details": [f"{report.get('path')}: {errors}"],
    }


def refine_validation_reports(review: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actionable: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []
    for report in review.get("validation_reports", []):
        if not report.get("exists"):
            actionable.append(
                {
                    "severity": "medium",
                    "area": "validation_reports",
                    "title": "Expected validation report is missing",
                    "details": [str(report.get("path"))],
                }
            )
            continue
        if report.get("passed") is False:
            classified = classify_ai_workload_failure(report)
            if classified["classification"] == "expected_guardrail":
                informational.append(classified)
            else:
                actionable.append(classified)
    return actionable, informational


def refine_doc_code(review: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repo_root = repo_root_from_review(review)
    missing = review.get("doc_code_consistency", {}).get("missing_path_references", []) or []
    actionable_refs = []
    ignored_refs = []
    resolved_refs = []
    for item in missing:
        doc = str(item.get("doc") or "")
        reference = str(item.get("reference") or "")
        normalized = normalize_reference(reference)
        resolved = existing_candidate(reference, repo_root)
        if doc in LOW_SIGNAL_DOCS:
            ignored_refs.append({**item, "normalized_reference": normalized, "reason": "low_signal_generated_history"})
        elif is_placeholder_reference(reference):
            ignored_refs.append({**item, "normalized_reference": normalized, "reason": "placeholder_generated_or_template_path"})
        elif resolved:
            resolved_refs.append({**item, "normalized_reference": normalized, "resolved_reference": resolved, "reason": "exists_after_normalization_or_alias"})
        elif is_conceptual_slash_term(reference):
            ignored_refs.append({**item, "normalized_reference": normalized, "reason": "conceptual_slash_term"})
        elif has_path_intent(reference):
            actionable_refs.append({**item, "normalized_reference": normalized, "candidate_references": candidate_references(reference)})
        else:
            ignored_refs.append({**item, "normalized_reference": normalized, "reason": "no_clear_path_intent"})
    findings = []
    if actionable_refs:
        findings.append(
            {
                "severity": "medium",
                "area": "doc_code",
                "title": "Markdown references likely repository paths that are missing",
                "details": [f"{item.get('doc')} -> {item.get('normalized_reference')}" for item in actionable_refs[:30]],
            }
        )
    return findings, {
        "actionable_refs": actionable_refs[:200],
        "resolved_count": len(resolved_refs),
        "resolved_sample": resolved_refs[:80],
        "ignored_count": len(ignored_refs),
        "ignored_sample": ignored_refs[:80],
    }


def refine_doc_doc(review: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    canonical_docs = review.get("doc_doc_consistency", {}).get("canonical_docs", []) or []
    actionable = []
    informational = []
    for item in canonical_docs:
        missing = list(item.get("missing_terms") or [])
        if not missing:
            continue
        path = str(item.get("path"))
        if path in {"docs/JSON_SCHEMAS.md", "Tools/validation/README.md", "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md"}:
            actionable.append({"path": path, "missing_terms": missing})
        else:
            informational.append({"path": path, "missing_terms": missing, "reason": "canonical_doc_not_required_to_repeat_all_contract_terms"})
    findings = []
    if actionable:
        findings.append(
            {
                "severity": "medium",
                "area": "doc_doc",
                "title": "Dedicated contract docs may need targeted cross-references",
                "details": [f"{item['path']}: {item['missing_terms']}" for item in actionable],
            }
        )
    return findings, {"actionable": actionable, "informational": informational}


def is_backup_or_generated_path(path: str) -> bool:
    return any(segment in path for segment in BACKUP_OR_GENERATED_SEGMENTS)


def path_group(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "Tools":
        return "/".join(parts[:2])
    if len(parts) >= 3 and parts[0] == "Scripting":
        return "/".join(parts[:2])
    return parts[0] if parts else path


def is_low_signal_duplicate(symbol: str, paths: list[str]) -> bool:
    if symbol in ALLOW_DUPLICATE_SYMBOLS:
        return True
    if symbol.startswith("_") and len(paths) <= 4:
        return True
    if symbol.startswith(("add_", "build_", "check_", "classify_", "configure_", "create_", "extract_", "find_", "format_")) and len(paths) <= 6:
        return True
    if any(is_backup_or_generated_path(path) for path in paths):
        return True
    groups = {path_group(path) for path in paths}
    if len(groups) > 1 and len(paths) <= 6:
        return True
    return False


def refine_code_code(review: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    duplicates = review.get("code_code_consistency", {}).get("duplicate_symbols", []) or []
    actionable = []
    ignored = []
    for item in duplicates:
        symbol = str(item.get("symbol") or "")
        paths = [str(path) for path in item.get("paths", [])]
        if is_low_signal_duplicate(symbol, paths):
            ignored.append({**item, "reason": "generic_generated_or_cross_package_duplicate"})
        elif paths and all(is_backup_or_generated_path(path) for path in paths):
            ignored.append({**item, "reason": "backup_or_generated_only"})
        elif any("Scripting/v61b_backgood/" in path for path in paths) and any("Scripting/v61b/" in path for path in paths):
            ignored.append({**item, "reason": "active_vs_backup_tree_duplicate"})
        else:
            actionable.append(item)
    findings = []
    if actionable:
        findings.append(
            {
                "severity": "low",
                "area": "code_code",
                "title": "Duplicate code symbols remain after generic/generated filtering",
                "details": [f"{item.get('symbol')} -> {item.get('paths')}" for item in actionable[:30]],
            }
        )
    return findings, {"actionable": actionable[:120], "ignored_count": len(ignored), "ignored_sample": ignored[:80]}


def build_proposals(findings: list[dict[str, Any]], review: dict[str, Any]) -> dict[str, Any]:
    proposals = []
    for finding in findings:
        if finding.get("severity") in {"high", "medium", "low"}:
            proposals.append(
                {
                    "id": f"REFINED-MEGA-{len(proposals)+1:03d}",
                    "title": finding.get("title"),
                    "area": finding.get("area"),
                    "apply_mode": "manual_review_only",
                    "content_status": "proposal_only",
                    "details": finding.get("details", []),
                }
            )
    return {
        "schema_version": 1,
        "kind": "megalithic_refined_review_proposals",
        "repo_root": review.get("repo_root"),
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": bool(review.get("provider_execution_performed")),
        "patch_application_performed": False,
        "apply_mode": "manual_review_only",
        "proposal_count": len(proposals),
        "proposals": proposals,
    }


def refine_review(review: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    validation_findings, validation_info = refine_validation_reports(review)
    doc_code_findings, doc_code_meta = refine_doc_code(review)
    doc_doc_findings, doc_doc_meta = refine_doc_doc(review)
    code_code_findings, code_code_meta = refine_code_code(review)
    findings = validation_findings + doc_code_findings + doc_doc_findings + code_code_findings
    informational = validation_info
    if not findings:
        findings.append(
            {
                "severity": "info",
                "area": "baseline",
                "title": "No high-confidence actionable discrepancy after signal refinement",
                "details": ["The wide megalithic scan produced only expected guardrails or low-signal findings."],
            }
        )
    refined = {
        "schema_version": 1,
        "kind": "megalithic_refined_review",
        "generated_at": now_iso(),
        "repo_root": review.get("repo_root"),
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": bool(review.get("provider_execution_performed")),
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_manual_review_only",
        "original_review_kind": review.get("kind"),
        "original_summary": review.get("summary", {}),
        "refined_findings": findings,
        "informational_findings": informational,
        "refinement": {
            "doc_code": doc_code_meta,
            "doc_doc": doc_doc_meta,
            "code_code": code_code_meta,
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_explicit_only": True,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "output_artifacts_should_not_be_committed": True,
            "sqlite_db_should_not_be_committed": True,
        },
    }
    proposals = build_proposals(findings, review)
    return refined, proposals


def render_markdown(refined: dict[str, Any], proposals: dict[str, Any]) -> str:
    lines = ["# Megalithic Review Signal Refinement", ""]
    lines.append(f"- Provider execution performed upstream: `{refined['provider_execution_performed']}`")
    lines.append(f"- Proposal count: `{proposals['proposal_count']}`")
    lines.append("")
    lines.append("## Refined findings")
    lines.append("")
    for finding in refined["refined_findings"]:
        lines.append(f"### {finding.get('severity')} — {finding.get('title')}")
        lines.append(f"- Area: `{finding.get('area')}`")
        for detail in finding.get("details", [])[:30]:
            lines.append(f"- {detail}")
        lines.append("")
    if refined.get("informational_findings"):
        lines.append("## Informational / expected guardrails")
        lines.append("")
        for finding in refined["informational_findings"]:
            lines.append(f"### {finding.get('title')}")
            for detail in finding.get("details", [])[:20]:
                lines.append(f"- {detail}")
            lines.append("")
    lines.append("## Refinement counters")
    lines.append("")
    lines.append(f"- Resolved doc/code refs: `{refined['refinement']['doc_code'].get('resolved_count', 0)}`")
    lines.append(f"- Ignored doc/code refs: `{refined['refinement']['doc_code']['ignored_count']}`")
    lines.append(f"- Ignored code/code duplicates: `{refined['refinement']['code_code']['ignored_count']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", default=DEFAULT_REVIEW)
    parser.add_argument("--proposals", default=DEFAULT_PROPOSALS, help="Original proposals artifact; currently read for provenance only.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--proposal-output", default=DEFAULT_PROPOSALS_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    review = read_json(Path(args.review))
    _original_proposals = read_json(Path(args.proposals)) if Path(args.proposals).exists() else {}
    refined, proposals = refine_review(review)
    write_json(Path(args.output), refined)
    write_json(Path(args.proposal_output), proposals)
    markdown_output = Path(args.markdown_output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(refined, proposals), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": refined["passed"],
                "output": args.output,
                "proposal_output": args.proposal_output,
                "markdown": args.markdown_output,
                "proposal_count": proposals["proposal_count"],
                "provider_execution_performed": refined["provider_execution_performed"],
                "patch_application_performed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
