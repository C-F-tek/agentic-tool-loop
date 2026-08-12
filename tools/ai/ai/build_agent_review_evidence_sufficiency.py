#!/usr/bin/env python3
"""Build an evidence-sufficiency review for megalithic findings.

This is an agnostic reasoning layer between a refined review and any future
patch. It inspects the refined findings, linked proposals, repository files and
optional agnostic context artifacts, then decides whether the evidence is enough
for a safe patch, needs more context, or should remain advisory-only.

The tool is report-only:

- no provider execution;
- no patch application;
- no GitHub PR creation;
- no SQLite writes;
- no persistent memory promotion.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from dataclasses import dataclass
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

DEFAULT_REFINED_REVIEW = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review.json"
DEFAULT_REFINED_PROPOSALS = "output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_proposals.json"
DEFAULT_OUTPUT = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_review_evidence_sufficiency.md"
MAX_SNIPPET_CHARS = 1600


@dataclass(frozen=True)
class EvidenceFile:
    """A repository file inspected as evidence."""

    path: str
    exists: bool
    kind: str
    chars: int = 0
    lines: int = 0
    matched_terms: tuple[str, ...] = ()
    snippet: str = ""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)



def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def load_json_object(path: Path) -> dict[str, Any]:
    data, errors = read_json_object(path)
    if errors:
        raise ValueError(f"{path}: {'; '.join(errors)}")
    return data


def compact_snippet(text: str, terms: list[str], *, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    """Return a compact snippet around the first matching term."""
    if not text:
        return ""
    lower = text.lower()
    positions = [lower.find(term.lower()) for term in terms if term and lower.find(term.lower()) >= 0]
    if positions:
        start = max(0, min(positions) - max_chars // 3)
    else:
        start = 0
    snippet = text[start : start + max_chars]
    return snippet.replace("\r\n", "\n")


def inspect_file(repo_root: Path, value: str, *, terms: list[str] | None = None, kind: str = "evidence") -> EvidenceFile:
    terms = terms or []
    path = resolve_path(repo_root, value)
    if not path.exists() or not path.is_file():
        return EvidenceFile(path=repo_rel(path, repo_root), exists=False, kind=kind)
    text = read_text(path)
    matched = tuple(term for term in terms if term and term.lower() in text.lower())
    return EvidenceFile(
        path=repo_rel(path, repo_root),
        exists=True,
        kind=kind,
        chars=len(text),
        lines=len(text.splitlines()),
        matched_terms=matched,
        snippet=compact_snippet(text, list(matched or terms)),
    )


def evidence_to_dict(item: EvidenceFile) -> dict[str, Any]:
    return {
        "path": item.path,
        "exists": item.exists,
        "kind": item.kind,
        "chars": item.chars,
        "lines": item.lines,
        "matched_terms": list(item.matched_terms),
        "snippet": item.snippet,
    }


def load_optional_report(repo_root: Path, value: str) -> dict[str, Any]:
    path = resolve_path(repo_root, value)
    out: dict[str, Any] = {"path": repo_rel(path, repo_root), "exists": path.exists(), "kind": None, "passed": None, "error": ""}
    if not path.exists():
        out["error"] = "missing"
        return out
    data, errors = read_json_object(path)
    if errors:
        out["error"] = "; ".join(errors)
        return out
    out["kind"] = data.get("kind")
    out["passed"] = data.get("passed")
    out["summary"] = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return out


def extract_doc_code_targets(refined: dict[str, Any]) -> list[dict[str, Any]]:
    targets = refined.get("refinement", {}).get("doc_code", {}).get("actionable_refs", []) or []
    return [item for item in targets if isinstance(item, dict)]


def extract_doc_doc_targets(refined: dict[str, Any]) -> list[dict[str, Any]]:
    targets = refined.get("refinement", {}).get("doc_doc", {}).get("actionable", []) or []
    return [item for item in targets if isinstance(item, dict)]


def normalize_candidate(candidate: Any) -> str:
    if candidate is None:
        return ""
    return str(candidate).replace("\\", "/").strip().strip("`.,:)];\"").lstrip("/")


def candidate_exists(repo_root: Path, candidates: list[Any]) -> tuple[str | None, list[str]]:
    normalized = [normalize_candidate(item) for item in candidates]
    for item in normalized:
        if item and (repo_root / item).exists():
            return item, normalized
    return None, normalized


def analyze_doc_code(refined: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    items = []
    ready = 0
    needs_context = 0
    for target in extract_doc_code_targets(refined):
        doc = str(target.get("doc") or "")
        normalized_ref = normalize_candidate(target.get("normalized_reference") or target.get("reference"))
        candidates = target.get("candidate_references") or [normalized_ref]
        existing, normalized_candidates = candidate_exists(repo_root, candidates)
        doc_evidence = inspect_file(repo_root, doc, terms=[normalized_ref, *normalized_candidates], kind="source_markdown")
        target_evidence = inspect_file(repo_root, existing or normalized_ref, terms=[], kind="target_path") if existing else inspect_file(repo_root, normalized_ref, kind="target_path")
        sufficient = doc_evidence.exists and normalized_ref and existing is None
        recommendation = "manual_doc_reference_patch_candidate" if sufficient else "needs_more_context"
        if sufficient:
            ready += 1
        else:
            needs_context += 1
        items.append(
            {
                "doc": doc,
                "reference": normalized_ref,
                "candidate_references": normalized_candidates,
                "existing_candidate": existing,
                "evidence_sufficient": sufficient,
                "recommendation": recommendation,
                "confidence": "medium" if sufficient else "low",
                "reason": "source doc exists and target path remains missing" if sufficient else "source doc missing or target resolved",
                "evidence_files": [evidence_to_dict(doc_evidence), evidence_to_dict(target_evidence)],
            }
        )
    return {
        "area": "doc_code",
        "item_count": len(items),
        "ready_for_manual_patch_count": ready,
        "needs_more_context_count": needs_context,
        "items": items,
    }


def analyze_doc_doc(refined: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    items = []
    ready = 0
    for target in extract_doc_doc_targets(refined):
        path = str(target.get("path") or "")
        terms = [str(item) for item in target.get("missing_terms", [])]
        evidence = inspect_file(repo_root, path, terms=terms, kind="contract_doc")
        sufficient = evidence.exists and bool(terms)
        if sufficient:
            ready += 1
        items.append(
            {
                "path": path,
                "missing_terms": terms,
                "evidence_sufficient": sufficient,
                "recommendation": "manual_cross_reference_patch_candidate" if sufficient else "needs_more_context",
                "confidence": "medium" if sufficient else "low",
                "reason": "contract doc exists and missing terms are explicit" if sufficient else "contract doc missing or no explicit terms",
                "evidence_files": [evidence_to_dict(evidence)],
            }
        )
    return {
        "area": "doc_doc",
        "item_count": len(items),
        "ready_for_manual_patch_count": ready,
        "needs_more_context_count": len(items) - ready,
        "items": items,
    }


def analyze_code_code(refined: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    targets = refined.get("refinement", {}).get("code_code", {}).get("actionable", []) or []
    items = []
    for target in targets:
        symbol = str(target.get("symbol") or "")
        paths = [str(path) for path in target.get("paths", [])]
        evidence_files = [evidence_to_dict(inspect_file(repo_root, path, terms=[symbol], kind="symbol_file")) for path in paths[:8]]
        items.append(
            {
                "symbol": symbol,
                "paths": paths,
                "evidence_sufficient": False,
                "recommendation": "advisory_only_until_semantic_equivalence_review",
                "confidence": "low",
                "reason": "duplicate symbol names alone are not enough to patch safely",
                "evidence_files": evidence_files,
            }
        )
    return {
        "area": "code_code",
        "item_count": len(items),
        "ready_for_manual_patch_count": 0,
        "needs_more_context_count": len(items),
        "items": items,
    }


def build_decision(doc_code: dict[str, Any], doc_doc: dict[str, Any], code_code: dict[str, Any]) -> dict[str, Any]:
    ready = doc_code["ready_for_manual_patch_count"] + doc_doc["ready_for_manual_patch_count"] + code_code["ready_for_manual_patch_count"]
    needs_context = doc_code["needs_more_context_count"] + doc_doc["needs_more_context_count"] + code_code["needs_more_context_count"]
    next_steps = []
    if doc_code["ready_for_manual_patch_count"]:
        next_steps.append("Review doc_code items and patch only source Markdown references with missing targets or intentional placeholders.")
    if doc_doc["ready_for_manual_patch_count"]:
        next_steps.append("Add targeted cross-references to dedicated contract docs instead of duplicating full contracts everywhere.")
    if code_code["item_count"]:
        next_steps.append("Keep code_code findings advisory-only until semantic equivalence is established.")
    return {
        "ready_for_manual_patch_count": ready,
        "needs_more_context_count": needs_context,
        "recommended_mode": "manual_review_only_patch_candidates" if ready else "no_patch_recommended",
        "sufficient_for_real_pr": ready > 0,
        "next_steps": next_steps,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    refined_path = resolve_path(repo_root, args.refined_review)
    proposals_path = resolve_path(repo_root, args.refined_proposals)
    if not refined_path.exists():
        missing = repo_rel(refined_path, repo_root)
        proposal_missing = not proposals_path.exists()
        return {
            "schema_version": 1,
            "kind": "agent_review_evidence_sufficiency",
            "generated_at": now_iso(),
            "repo_root": str(repo_root),
            "passed": False,
            "errors": [f"blocked_missing_refined_review_input: {missing}"],
            "warnings": [
                "Evidence sufficiency input is missing; Full0To10 must classify this instead of raising a traceback.",
            ],
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "apply_mode": "report_only_evidence_sufficiency",
            "inputs": {
                "refined_review": missing,
                "refined_review_exists": False,
                "refined_proposals": repo_rel(proposals_path, repo_root),
                "refined_proposals_exists": not proposal_missing,
                "refined_proposal_count": None,
                "context_reports": [load_optional_report(repo_root, value) for value in args.report_file],
            },
            "areas": {
                "doc_code": {"area": "doc_code", "item_count": 0, "ready_for_manual_patch_count": 0, "needs_more_context_count": 0, "items": []},
                "doc_doc": {"area": "doc_doc", "item_count": 0, "ready_for_manual_patch_count": 0, "needs_more_context_count": 0, "items": []},
                "code_code": {"area": "code_code", "item_count": 0, "ready_for_manual_patch_count": 0, "needs_more_context_count": 0, "items": []},
            },
            "decision": {
                "ready_for_manual_patch_count": 0,
                "needs_more_context_count": 0,
                "recommended_mode": "blocked_missing_refined_review_input",
                "sufficient_for_real_pr": False,
                "next_steps": ["Generate refined review/proposals or rewire this lane to current-run reports before acceptance."],
            },
            "guardrails": {
                "report_only": True,
                "provider_execution_performed": False,
                "patch_application_performed": False,
                "real_github_pr_created": False,
                "sqlite_write_performed": False,
                "persistent_memory_write_performed": False,
                "manual_review_required": True,
            },
        }
    refined = load_json_object(refined_path)
    proposals = load_json_object(proposals_path) if proposals_path.exists() else {}
    doc_code = analyze_doc_code(refined, repo_root)
    doc_doc = analyze_doc_doc(refined, repo_root)
    code_code = analyze_code_code(refined, repo_root)
    decision = build_decision(doc_code, doc_doc, code_code)
    context_reports = [load_optional_report(repo_root, value) for value in args.report_file]
    warnings = [f"context report missing/unreadable: {item['path']} ({item['error']})" for item in context_reports if item.get("error")]
    return {
        "schema_version": 1,
        "kind": "agent_review_evidence_sufficiency",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_evidence_sufficiency",
        "inputs": {
            "refined_review": repo_rel(refined_path, repo_root),
            "refined_proposals": repo_rel(proposals_path, repo_root),
            "refined_proposal_count": proposals.get("proposal_count"),
            "context_reports": context_reports,
        },
        "areas": {
            "doc_code": doc_code,
            "doc_doc": doc_doc,
            "code_code": code_code,
        },
        "decision": decision,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "manual_review_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Evidence Sufficiency", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Recommended mode: `{report['decision']['recommended_mode']}`")
    lines.append(f"- Sufficient for real PR: `{report['decision']['sufficient_for_real_pr']}`")
    lines.append(f"- Ready patch candidates: `{report['decision']['ready_for_manual_patch_count']}`")
    lines.append(f"- Needs more context: `{report['decision']['needs_more_context_count']}`")
    lines.append("")
    for step in report["decision"].get("next_steps", []):
        lines.append(f"- {step}")
    lines.append("")
    for area_name, area in report["areas"].items():
        lines.append(f"## {area_name}")
        lines.append("")
        lines.append(f"- Items: `{area['item_count']}`")
        lines.append(f"- Ready: `{area['ready_for_manual_patch_count']}`")
        lines.append(f"- Needs context: `{area['needs_more_context_count']}`")
        lines.append("")
        for item in area.get("items", [])[:20]:
            label = item.get("path") or item.get("doc") or item.get("symbol")
            lines.append(f"### {label}")
            lines.append(f"- Recommendation: `{item.get('recommendation')}`")
            lines.append(f"- Evidence sufficient: `{item.get('evidence_sufficient')}`")
            lines.append(f"- Confidence: `{item.get('confidence')}`")
            lines.append(f"- Reason: {item.get('reason')}")
            if item.get("reference"):
                lines.append(f"- Reference: `{item.get('reference')}`")
            if item.get("missing_terms"):
                lines.append(f"- Missing terms: `{item.get('missing_terms')}`")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--refined-review", default=DEFAULT_REFINED_REVIEW)
    parser.add_argument("--refined-proposals", default=DEFAULT_REFINED_PROPOSALS)
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
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
                "ready_for_manual_patch_count": report["decision"]["ready_for_manual_patch_count"],
                "needs_more_context_count": report["decision"]["needs_more_context_count"],
                "sufficient_for_real_pr": report["decision"]["sufficient_for_real_pr"],
                "provider_execution_performed": False,
                "patch_application_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
