#!/usr/bin/env python3
"""Synthesize schema-valid GPU planner recommendations from evidence reports.

This tool is deliberately deterministic and report-only. It is the bridge between
runtime evidence/tool reports and the GPU planner JSON recommendation contract
when the provider returned zero usable recommendations because of parse or schema
failures.

It never executes providers, never applies patches, never writes SQLite memory,
never runs Blender and never creates GitHub PRs.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import normalize_repo_path, read_json_object
    from Tools.ai.gpu_planner_json_contract import validate_recommendation_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import normalize_repo_path, read_json_object  # type: ignore
    from Tools.ai.gpu_planner_json_contract import validate_recommendation_object  # type: ignore
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore

DEFAULT_EVIDENCE = "output/ai_pipeline/agent_review_evidence_sufficiency.json"
DEFAULT_ORCHESTRATOR = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator_live.json"
DEFAULT_OUTPUT = "output/ai_pipeline/deterministic_recommendations.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/deterministic_recommendations.md"

REPORT_KIND = "deterministic_recommendation_synthesizer"
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
    "docs/LOCAL_VALIDATION_EVIDENCE/",
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
    return path.resolve(strict=False)


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def load_report(path: Path, *, missing_is_error: bool = True) -> tuple[dict[str, Any], list[str]]:
    data, errors = read_json_object(path, missing_is_error=missing_is_error)
    return data, [f"{repo_rel(path, path.parents[0])}: {error}" for error in errors]


def load_report_at(repo_root: Path, value: str | Path, *, missing_is_error: bool = True) -> tuple[dict[str, Any], list[str]]:
    path = resolve_path(repo_root, value)
    data, errors = read_json_object(path, missing_is_error=missing_is_error)
    return data, [f"{repo_rel(path, repo_root)}: {error}" for error in errors]


def unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
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
    full = (repo_root / normalized).resolve(strict=False)
    try:
        full.relative_to(repo_root.resolve(strict=False))
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


def evidence_ready_for_manual_patch_count(evidence: dict[str, Any]) -> int:
    explicit_counts: list[int] = []
    ready_items = 0

    def visit(value: Any) -> None:
        nonlocal ready_items
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "ready_for_manual_patch_count" and isinstance(child, int):
                    explicit_counts.append(child)
                visit(child)
            if value.get("evidence_sufficient") is True:
                ready_items += 1
            status = value.get("status") or value.get("classification")
            if isinstance(status, str) and status in {"ready_for_manual_patch", "ready_for_patch_plan"}:
                ready_items += 1
            decision = value.get("decision")
            if isinstance(decision, dict):
                if decision.get("ready_for_manual_patch") is True or decision.get("ready_for_patch_plan") is True:
                    ready_items += 1
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(evidence)
    if explicit_counts:
        return max(explicit_counts)
    return ready_items


def compact_evidence_files(item: dict[str, Any]) -> list[str]:
    compact: list[str] = []
    raw = item.get("evidence_files")
    if not isinstance(raw, list):
        return compact
    for evidence_file in raw[:8]:
        if not isinstance(evidence_file, dict):
            continue
        path = normalize_repo_path(evidence_file.get("path"))
        if path:
            compact.append(path)
    return compact


def npu_audit_refs(orchestrator: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    raw_audits = orchestrator.get("npu_audits")
    if not isinstance(raw_audits, list):
        return refs
    for audit in raw_audits[:8]:
        if not isinstance(audit, dict):
            continue
        refs.append(
            {
                "round": audit.get("round"),
                "status": audit.get("status"),
                "classification": audit.get("classification"),
                "runtime_tool_context_seen": audit.get("runtime_tool_context_seen"),
                "npu_tool_request_count": audit.get("npu_tool_request_count"),
                "npu_runtime_tool_execution_count": audit.get("npu_runtime_tool_execution_count"),
                "npu_runtime_tool_failed_count": audit.get("npu_runtime_tool_failed_count"),
                "npu_runtime_tool_blocked_count": audit.get("npu_runtime_tool_blocked_count"),
            }
        )
    return refs


def summarize_tool_report(path: Path, repo_root: Path, data: dict[str, Any]) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "path": repo_rel(path, repo_root),
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "tool_request_count": data.get("tool_request_count") or summary.get("tool_request_count"),
        "tool_execution_count": data.get("tool_execution_count") or summary.get("tool_execution_count"),
        "failed_tool_count": data.get("failed_tool_count") or summary.get("failed_tool_count"),
        "blocked_tool_count": data.get("blocked_tool_count") or summary.get("blocked_tool_count"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "patch_application_performed": data.get("patch_application_performed"),
    }


def recommendation_schema_errors(rec: dict[str, Any], index: int, repo_root: Path) -> list[str]:
    errors = validate_recommendation_object(rec, index)
    for target in rec.get("target_files", []) if isinstance(rec.get("target_files"), list) else []:
        target_error = target_path_error(str(target), repo_root)
        if target_error:
            errors.append(f"recommendations[{index}].target_files {target!r}: {target_error}")
    return errors


def recommendation_key(rec: dict[str, Any]) -> str:
    return json.dumps(
        [
            rec.get("area"),
            rec.get("status"),
            rec.get("target_files"),
            rec.get("proposed_strategy"),
        ],
        sort_keys=True,
        ensure_ascii=False,
    )


def provider_recommendations(gpu_report: dict[str, Any], repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    recommendations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    raw = gpu_report.get("recommendations")
    if not isinstance(raw, list):
        return recommendations, skipped
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            skipped.append({"id": f"provider_{index:03d}", "reason": "recommendation is not an object"})
            continue
        if item.get("status") != "ready_for_patch_plan":
            continue
        rec = dict(item)
        rec.setdefault("source", "gpu_provider")
        errors = recommendation_schema_errors(rec, len(recommendations), repo_root)
        if errors:
            skipped.append({"id": str(item.get("id") or f"provider_{index:03d}"), "reason": "; ".join(errors)})
            continue
        recommendations.append(rec)
    return recommendations, skipped


def doc_code_recommendation(
    *,
    item: dict[str, Any],
    index: int,
    repo_root: Path,
    npu_refs: list[dict[str, Any]],
    tool_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    doc = normalize_repo_path(item.get("doc"))
    if not doc:
        return None, {"id": f"det_doc_code_{index:03d}", "reason": "doc_code item has no doc target"}
    error = target_path_error(doc, repo_root)
    if error:
        return None, {"id": f"det_doc_code_{index:03d}", "reason": f"{doc}: {error}"}

    reference = normalize_repo_path(item.get("reference"))
    existing_candidate = normalize_repo_path(item.get("existing_candidate"))
    candidates = unique_strings(item.get("candidate_references"))
    evidence_paths = compact_evidence_files(item)
    strategy_parts = [
        "Create a narrow manual-review patch plan for the documentation/code reference mismatch.",
        f"Inspect `{reference}` and update `{doc}` only if the reference is stale or should point at an existing artifact.",
    ]
    if existing_candidate:
        strategy_parts.append(f"Prefer existing candidate `{existing_candidate}` over inventing a new runtime artifact.")
    if candidates:
        strategy_parts.append(f"Candidate references observed: {', '.join(f'`{candidate}`' for candidate in candidates[:6])}.")

    return (
        {
            "id": f"det_doc_code_{index:03d}",
            "area": "doc_code",
            "status": "ready_for_patch_plan",
            "target_files": [doc],
            "rationale": item.get("reason")
            or "Evidence and runtime tool reports are sufficient to build a manual-review patch plan for this doc/code reference.",
            "proposed_strategy": " ".join(strategy_parts),
            "risk": "low",
            "validation_commands": DEFAULT_VALIDATION_COMMANDS,
            "stop_conditions": [
                "Stop if the referenced file exists after refreshing master.",
                "Stop if the fix requires creating runtime code instead of correcting documentation or references.",
                "Stop if the patch would touch output/**, generated indexes, SQLite, full analysis JSON, provider settings or Blender runtime.",
            ],
            "source": "deterministic_evidence_synthesizer",
            "evidence": evidence_paths,
            "tool_evidence": tool_refs,
            "npu_audit_refs": npu_refs,
            "guardrails": {
                "patch_application_performed": False,
                "manual_review_required": True,
            },
        },
        None,
    )


def doc_doc_recommendation(
    *,
    item: dict[str, Any],
    index: int,
    repo_root: Path,
    npu_refs: list[dict[str, Any]],
    tool_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    path = normalize_repo_path(item.get("path"))
    if not path:
        return None, {"id": f"det_doc_doc_{index:03d}", "reason": "doc_doc item has no path target"}
    error = target_path_error(path, repo_root)
    if error:
        return None, {"id": f"det_doc_doc_{index:03d}", "reason": f"{path}: {error}"}
    missing_terms = [str(term) for term in item.get("missing_terms", []) if str(term).strip()] if isinstance(item.get("missing_terms"), list) else []
    terms_text = ", ".join(f"`{term}`" for term in missing_terms[:10]) or "the missing cross-reference terms"
    return (
        {
            "id": f"det_doc_doc_{index:03d}",
            "area": "doc_doc",
            "status": "ready_for_patch_plan",
            "target_files": [path],
            "rationale": item.get("reason")
            or "Evidence and runtime tool reports are sufficient to build a manual-review documentation cross-reference patch plan.",
            "proposed_strategy": (
                f"Add a compact cross-reference for {terms_text}. "
                "Link or summarize the canonical source instead of duplicating large contract sections."
            ),
            "risk": "low",
            "validation_commands": DEFAULT_VALIDATION_COMMANDS,
            "stop_conditions": [
                "Stop if the missing terms are already present after refreshing master.",
                "Stop if the edit would duplicate large generated artifacts.",
                "Stop if the patch would touch output/**, generated indexes, SQLite, full analysis JSON, provider settings or Blender runtime.",
            ],
            "source": "deterministic_evidence_synthesizer",
            "evidence": compact_evidence_files(item),
            "tool_evidence": tool_refs,
            "npu_audit_refs": npu_refs,
            "guardrails": {
                "patch_application_performed": False,
                "manual_review_required": True,
            },
        },
        None,
    )


def synthesize_from_evidence(
    *,
    evidence: dict[str, Any],
    repo_root: Path,
    npu_refs: list[dict[str, Any]],
    tool_refs: list[dict[str, Any]],
    max_recommendations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    recommendations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    areas = evidence.get("areas") if isinstance(evidence.get("areas"), dict) else {}

    doc_code = areas.get("doc_code") if isinstance(areas.get("doc_code"), dict) else {}
    for index, item in enumerate(doc_code.get("items", []) if isinstance(doc_code.get("items"), list) else [], start=1):
        if len(recommendations) >= max_recommendations:
            break
        if not isinstance(item, dict) or item.get("evidence_sufficient") is not True:
            continue
        rec, skip = doc_code_recommendation(
            item=item,
            index=index,
            repo_root=repo_root,
            npu_refs=npu_refs,
            tool_refs=tool_refs,
        )
        if rec:
            recommendations.append(rec)
        if skip:
            skipped.append(skip)

    doc_doc = areas.get("doc_doc") if isinstance(areas.get("doc_doc"), dict) else {}
    for index, item in enumerate(doc_doc.get("items", []) if isinstance(doc_doc.get("items"), list) else [], start=1):
        if len(recommendations) >= max_recommendations:
            break
        if not isinstance(item, dict) or item.get("evidence_sufficient") is not True:
            continue
        rec, skip = doc_doc_recommendation(
            item=item,
            index=index,
            repo_root=repo_root,
            npu_refs=npu_refs,
            tool_refs=tool_refs,
        )
        if rec:
            recommendations.append(rec)
        if skip:
            skipped.append(skip)

    validated: list[dict[str, Any]] = []
    for rec in recommendations:
        errors = recommendation_schema_errors(rec, len(validated), repo_root)
        if errors:
            skipped.append({"id": str(rec.get("id")), "reason": "; ".join(errors)})
            continue
        validated.append(rec)
    return validated, skipped


SUBSTANTIVE_CONSISTENCY_FINDING_PRIORITIES = {
    "python_import_missing": 10,
    "md_python_command_script_missing": 20,
    "md_mentions_missing_powershell_path": 30,
    "md_cli_arg_not_in_argparse": 40,
    "md_mentions_missing_python_path": 50,
    "md_mentions_missing_markdown_path": 60,
    "documented_python_script_without_obvious_smoke": 70,
}
COSMETIC_FINDING_KEYWORDS = (
    "whitespace",
    "space-only",
    "spacing-only",
    "tag spacing",
    "tag-spacing",
    "formatting-only",
    "cosmetic",
)


def severity_rank(value: Any) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(value or "").lower(), 3)


def finding_priority(finding: dict[str, Any]) -> tuple[int, int, str, int]:
    kind = str(finding.get("kind") or "")
    return (
        severity_rank(finding.get("severity")),
        SUBSTANTIVE_CONSISTENCY_FINDING_PRIORITIES.get(kind, 999),
        normalize_repo_path(finding.get("source")),
        int(finding.get("line") or 0),
    )


def is_cosmetic_consistency_finding(finding: dict[str, Any]) -> bool:
    text = " ".join(
        str(finding.get(key) or "")
        for key in ("kind", "severity", "source", "target", "flag", "evidence", "recommendation")
    ).lower()
    return any(keyword in text for keyword in COSMETIC_FINDING_KEYWORDS)


def consistency_target_file(finding: dict[str, Any], repo_root: Path) -> tuple[str, str | None]:
    source = normalize_repo_path(finding.get("source"))
    if source:
        source_error = target_path_error(source, repo_root)
        if source_error is None:
            return source, None
        return "", f"source {source!r}: {source_error}"
    target = normalize_repo_path(finding.get("target"))
    if target:
        target_error = target_path_error(target, repo_root)
        if target_error is None:
            return target, None
        return "", f"target {target!r}: {target_error}"
    return "", "finding has neither source nor target"


def consistency_area(kind: str) -> str:
    if kind == "python_import_missing":
        return "python_python"
    if kind in {"md_python_command_script_missing", "md_cli_arg_not_in_argparse", "md_mentions_missing_python_path"}:
        return "md_python"
    if kind == "md_mentions_missing_powershell_path":
        return "md_powershell"
    if kind == "md_mentions_missing_markdown_path":
        return "md_md"
    if kind == "documented_python_script_without_obvious_smoke":
        return "python_validation"
    return "repository_consistency"


def consistency_validation_commands(target_file: str) -> list[str]:
    commands = list(DEFAULT_VALIDATION_COMMANDS)
    if target_file.endswith(".py"):
        commands.insert(0, f"python -m py_compile {target_file}")
    return commands


def repository_consistency_recommendation(
    *,
    finding: dict[str, Any],
    index: int,
    repo_root: Path,
    tool_refs: list[dict[str, Any]],
    npu_refs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    kind = str(finding.get("kind") or "")
    if kind not in SUBSTANTIVE_CONSISTENCY_FINDING_PRIORITIES:
        return None, {"id": f"consistency_{index:03d}", "reason": f"unsupported finding kind: {kind}"}
    if is_cosmetic_consistency_finding(finding):
        return None, {"id": f"consistency_{index:03d}", "reason": "cosmetic/whitespace-only finding skipped"}
    target_file, target_error = consistency_target_file(finding, repo_root)
    if target_error:
        return None, {"id": f"consistency_{index:03d}", "reason": target_error}

    source = normalize_repo_path(finding.get("source"))
    target = normalize_repo_path(finding.get("target"))
    flag = str(finding.get("flag") or "")
    line = int(finding.get("line") or 0)
    severity = str(finding.get("severity") or "medium")
    evidence = str(finding.get("evidence") or "")
    recommendation = str(finding.get("recommendation") or "Resolve the repository consistency finding with the narrowest safe patch.")
    area = consistency_area(kind)
    risk = "medium" if severity == "high" else "low"
    evidence_label = f"{source}:{line}" if line else source or target_file
    mismatch = flag or target or kind
    strategy = (
        f"Build a focused patch plan for `{kind}` using mapper evidence `{evidence_label}`. "
        f"Target `{target_file}` and resolve `{mismatch}` without formatting-only edits. "
        f"Mapper recommendation: {recommendation}"
    )

    return (
        {
            "id": f"consistency_{index:03d}",
            "area": area,
            "status": "ready_for_patch_plan",
            "target_files": [target_file],
            "rationale": f"Repository consistency mapper reported {severity} `{kind}` at `{evidence_label}` targeting `{mismatch}`.",
            "proposed_strategy": strategy,
            "risk": risk,
            "validation_commands": consistency_validation_commands(target_file),
            "stop_conditions": [
                "Stop if the edit is only whitespace, tag spacing or Markdown formatting without fixing the cited finding.",
                "Stop if the target/source evidence no longer exists after refreshing master.",
                "Stop if the fix would touch output/**, generated indexes, SQLite, provider settings or Blender runtime.",
                "Stop if resolving the finding requires inventing behavior not supported by code evidence.",
            ],
            "source": "repository_consistency_map",
            "evidence": [evidence_label] if evidence_label else [],
            "tool_evidence": tool_refs,
            "npu_audit_refs": npu_refs,
            "repository_consistency_finding": {
                "kind": kind,
                "severity": severity,
                "source": source,
                "line": line,
                "target": target,
                "flag": flag,
                "evidence": evidence[:500],
            },
            "guardrails": {
                "patch_application_performed": False,
                "manual_review_required": True,
                "cosmetic_patch_allowed": False,
            },
        },
        None,
    )


def synthesize_from_repository_consistency_maps(
    *,
    repository_maps: list[dict[str, Any]],
    repo_root: Path,
    npu_refs: list[dict[str, Any]],
    tool_refs: list[dict[str, Any]],
    max_recommendations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    findings: list[dict[str, Any]] = []
    for repository_map in repository_maps:
        raw_findings = repository_map.get("findings")
        if not isinstance(raw_findings, list):
            continue
        for item in raw_findings:
            if isinstance(item, dict):
                findings.append(item)
    findings = sorted(findings, key=finding_priority)

    recommendations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen_targets: set[tuple[str, str, str]] = set()
    for index, finding in enumerate(findings, start=1):
        if len(recommendations) >= max_recommendations:
            break
        rec, skip = repository_consistency_recommendation(
            finding=finding,
            index=index,
            repo_root=repo_root,
            tool_refs=tool_refs,
            npu_refs=npu_refs,
        )
        if skip:
            skipped.append(skip)
        if not rec:
            continue
        dedupe_key = (str(rec.get("area")), str(rec.get("target_files")), str(rec.get("rationale")))
        if dedupe_key in seen_targets:
            continue
        errors = recommendation_schema_errors(rec, len(recommendations), repo_root)
        if errors:
            skipped.append({"id": str(rec.get("id")), "reason": "; ".join(errors)})
            continue
        seen_targets.add(dedupe_key)
        recommendations.append(rec)
    return recommendations, skipped

def load_gpu_report(repo_root: Path, orchestrator: dict[str, Any], explicit_gpu_report: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if explicit_gpu_report:
        data, errors = load_report_at(repo_root, explicit_gpu_report, missing_is_error=True)
        return data, errors

    gpu_output = normalize_repo_path(orchestrator.get("gpu_output"))
    if gpu_output:
        data, errors = load_report_at(repo_root, gpu_output, missing_is_error=True)
        warnings.extend(errors)
        return data, warnings

    default_path = resolve_path(repo_root, "output/ai_pipeline/agent_gpu_deep_planning_supervised.json")
    if default_path.exists():
        data, errors = load_report_at(repo_root, default_path, missing_is_error=False)
        warnings.extend(errors)
        return data, warnings
    return {}, warnings


def build_recommendation_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    evidence, evidence_errors = load_report_at(repo_root, args.evidence, missing_is_error=True)
    errors.extend(evidence_errors)

    orchestrator: dict[str, Any] = {}
    if args.orchestrator:
        orchestrator_path = resolve_path(repo_root, args.orchestrator)
        if orchestrator_path.exists():
            orchestrator, orchestrator_errors = load_report_at(repo_root, args.orchestrator, missing_is_error=False)
            warnings.extend(orchestrator_errors)
        else:
            warnings.append(f"orchestrator report missing: {repo_rel(orchestrator_path, repo_root)}")

    gpu_report, gpu_warnings = load_gpu_report(repo_root, orchestrator, args.gpu_report)
    warnings.extend(gpu_warnings)

    tool_refs: list[dict[str, Any]] = []
    repository_consistency_maps: list[dict[str, Any]] = []
    for value in args.tool_report:
        path = resolve_path(repo_root, value)
        data, tool_errors = load_report_at(repo_root, value, missing_is_error=False)
        warnings.extend(tool_errors)
        if data:
            tool_refs.append(summarize_tool_report(path, repo_root, data))
            if data.get("kind") == "repository_consistency_map":
                repository_consistency_maps.append(data)

    npu_refs = npu_audit_refs(orchestrator)
    provider_recs, provider_skipped = provider_recommendations(gpu_report, repo_root)
    recommendations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = list(provider_skipped)
    seen: set[str] = set()

    for rec in provider_recs:
        key = recommendation_key(rec)
        if key not in seen:
            seen.add(key)
            recommendations.append(rec)

    deterministic_used = False
    consistency_recommendation_count = 0
    if not recommendations and repository_consistency_maps:
        deterministic_used = True
        consistency_synthesized, consistency_skipped = synthesize_from_repository_consistency_maps(
            repository_maps=repository_consistency_maps,
            repo_root=repo_root,
            npu_refs=npu_refs,
            tool_refs=tool_refs,
            max_recommendations=args.max_recommendations,
        )
        skipped.extend(consistency_skipped)
        for rec in consistency_synthesized:
            key = recommendation_key(rec)
            if key not in seen:
                seen.add(key)
                recommendations.append(rec)
        consistency_recommendation_count = len(recommendations)

    if not recommendations and evidence:
        deterministic_used = True
        synthesized, synthesized_skipped = synthesize_from_evidence(
            evidence=evidence,
            repo_root=repo_root,
            npu_refs=npu_refs,
            tool_refs=tool_refs,
            max_recommendations=args.max_recommendations,
        )
        skipped.extend(synthesized_skipped)
        for rec in synthesized:
            key = recommendation_key(rec)
            if key not in seen:
                seen.add(key)
                recommendations.append(rec)

    if not recommendations and not errors:
        errors.append("no schema-valid recommendations were produced")

    evidence_ready_count = evidence_ready_for_manual_patch_count(evidence)
    empty_reason = (
        gpu_report.get("empty_recommendations_reason")
        or orchestrator.get("gpu_empty_recommendations_reason")
        or ""
    )
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
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "missing_evidence": [] if recommendations else ["no evidence-sufficient items with safe existing targets"],
        "next_best_action": "build_agent_review_patch_plan.py" if recommendations else "collect_more_evidence",
        "skipped_candidate_count": len(skipped),
        "skipped_candidates": skipped,
        "decision": {
            "deterministic_synthesizer_used": deterministic_used,
            "provider_recommendation_count": len(provider_recs),
            "schema_valid_recommendation_count": len(recommendations),
            "evidence_ready_for_manual_patch_count": evidence_ready_count,
            "gpu_empty_recommendations_reason": empty_reason,
            "ready_for_patch_plan": bool(recommendations),
            "repository_consistency_map_count": len(repository_consistency_maps),
            "substantive_consistency_recommendation_count": consistency_recommendation_count,
            "cosmetic_patch_suppression_enabled": True,
            "recommended_next_layer": "build_agent_review_patch_plan.py" if recommendations else "collect_more_evidence",
            "manual_review_required": True,
        },
        "inputs": {
            "evidence": normalize_repo_path(args.evidence),
            "orchestrator": normalize_repo_path(args.orchestrator),
            "gpu_report": normalize_repo_path(args.gpu_report) or normalize_repo_path(orchestrator.get("gpu_output")),
            "tool_report_count": len(args.tool_report),
            "repository_consistency_map_count": len(repository_consistency_maps),
            "evidence_kind": evidence.get("kind"),
            "orchestrator_kind": orchestrator.get("kind"),
            "gpu_kind": gpu_report.get("kind"),
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


def build_patch_plan_bridge_orchestrator(
    *,
    repo_root: Path,
    recommendation_report: dict[str, Any],
    recommendation_output: Path,
    source_orchestrator: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_orchestrator = source_orchestrator if isinstance(source_orchestrator, dict) else {}
    return {
        "schema_version": 1,
        "kind": "deterministic_recommendation_patch_plan_bridge_orchestrator",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": recommendation_report.get("passed"),
        "errors": list(recommendation_report.get("errors") or []),
        "warnings": list(recommendation_report.get("warnings") or []),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "gpu_output": repo_rel(recommendation_output, repo_root),
        "gpu_recommendation_count": recommendation_report.get("recommendation_count", 0),
        "gpu_empty_recommendations_reason": "",
        "gpu_recommended_next_layer": "build_agent_review_patch_plan.py",
        "npu_audits": source_orchestrator.get("npu_audits", []),
        "decision": {
            "deterministic_recommendation_bridge": True,
            "manual_review_required": True,
            "recommended_next_layer": "build_agent_review_patch_plan.py",
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
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Deterministic Recommendation Synthesizer", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Recommendation count: `{report['recommendation_count']}`")
    lines.append(f"- Deterministic synthesizer used: `{report['decision']['deterministic_synthesizer_used']}`")
    lines.append(f"- GPU empty recommendations reason: `{report['decision']['gpu_empty_recommendations_reason']}`")
    lines.append(f"- Evidence ready for manual patch count: `{report['decision']['evidence_ready_for_manual_patch_count']}`")
    lines.append(f"- Next best action: `{report['next_best_action']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    if not report.get("recommendations"):
        lines.append("- none")
    for rec in report.get("recommendations", []):
        lines.append(f"### {rec.get('id')} — {rec.get('area')}")
        lines.append(f"- Source: `{rec.get('source')}`")
        lines.append(f"- Status: `{rec.get('status')}`")
        lines.append(f"- Risk: `{rec.get('risk')}`")
        lines.append(f"- Target files: `{rec.get('target_files')}`")
        lines.append(f"- Rationale: {rec.get('rationale')}")
        lines.append(f"- Strategy: {rec.get('proposed_strategy')}")
        lines.append("")
    if report.get("skipped_candidates"):
        lines.append("## Skipped candidates")
        lines.append("")
        for item in report["skipped_candidates"]:
            lines.append(f"- `{item.get('id')}`: {item.get('reason')}")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("This report is deterministic and report-only. It is not a patch queue.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--orchestrator", default=DEFAULT_ORCHESTRATOR)
    parser.add_argument("--gpu-report", default="")
    parser.add_argument("--tool-report", action="append", default=[])
    parser.add_argument("--max-recommendations", type=int, default=20)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--patch-plan-orchestrator-output", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_recommendation_report(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)

    bridge_output_text = ""
    if args.patch_plan_orchestrator_output:
        source_orchestrator, _bridge_warnings = load_report_at(repo_root, args.orchestrator, missing_is_error=False)
        bridge_output = resolve_path(repo_root, args.patch_plan_orchestrator_output)
        bridge = build_patch_plan_bridge_orchestrator(
            repo_root=repo_root,
            recommendation_report=report,
            recommendation_output=output,
            source_orchestrator=source_orchestrator,
        )
        write_json_report(bridge, bridge_output)
        bridge_output_text = str(bridge_output)

    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "patch_plan_orchestrator_output": bridge_output_text,
                "recommendation_count": report["recommendation_count"],
                "deterministic_synthesizer_used": report["decision"]["deterministic_synthesizer_used"],
                "next_best_action": report["next_best_action"],
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
