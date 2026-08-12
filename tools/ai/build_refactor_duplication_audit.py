#!/usr/bin/env python3
"""Build a report-only refactor/duplication audit for IA-Carmine tools.

This tool is intentionally deterministic and provider-free. It inspects Python
files and existing JSON reports, classifies repeated helper/function patterns,
verifies the shared-toolbox evidence-bundle layering introduced by PR #142, and
emits JSON/Markdown evidence for manual review.

It does not execute providers, apply patches, run Blender, write SQLite memory,
or modify source files.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from Tools.validation.report_utils import read_json_report, resolve_output_path, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import read_json_report, resolve_output_path, write_json_report


DEFAULT_OUTPUT = "output/analysis/refactor_duplication_audit.json"
DEFAULT_MARKDOWN = "output/analysis/refactor_duplication_audit.md"
DEFAULT_ROOTS: tuple[str, ...] = ("Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu")
DEFAULT_EXCLUDE_PARTS: tuple[str, ...] = ("__pycache__", ".venv", "venv", ".git")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")

HELPER_RULES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "dup_path_helpers",
        "name_pattern": re.compile(r"^(repo_rel|repo_relative|resolve_path|resolve_repo_path|normalize_repo_path|normalize_manifest_path)$"),
        "repeated_logic": "Repository-relative and path resolution helper patterns.",
        "existing_helper_available": True,
        "preferred_existing_helper_or_module": "Tools.ai.github_evidence_bundle_io for evidence-bundle paths; Tools.validation.report_utils for validation output paths.",
        "recommendation_type": "reuse_existing_helper",
        "risk": "medium",
        "schema_or_cli_impact": "none expected if imports preserve path normalization semantics.",
    },
    {
        "candidate_id": "dup_json_text_helpers",
        "name_pattern": re.compile(r"^(read_json|read_json_if_exists|write_json|write_text|write_json_report)$"),
        "repeated_logic": "JSON/text read-write helpers repeated across report scripts and smoke tests.",
        "existing_helper_available": True,
        "preferred_existing_helper_or_module": "Tools.validation.report_utils.write_json_report plus existing evidence-bundle IO helpers for read paths.",
        "recommendation_type": "promote_existing_function",
        "risk": "low",
        "schema_or_cli_impact": "none if UTF-8 and JSON indentation are preserved.",
    },
    {
        "candidate_id": "dup_markdown_renderers",
        "name_pattern": re.compile(r"^(render_markdown|build_markdown|render_.*markdown)$"),
        "repeated_logic": "Local Markdown renderers with repeated status/guardrail sections.",
        "existing_helper_available": False,
        "preferred_existing_helper_or_module": "Keep report-specific renderers local unless a stable shared status-section schema emerges.",
        "recommendation_type": "keep_local_by_design",
        "risk": "low",
        "schema_or_cli_impact": "none; markdown is presentation-only but should remain reviewable.",
    },
    {
        "candidate_id": "dup_split_compact_helpers",
        "name_pattern": re.compile(r"^(split_values|split_path_values|coalesce_list|compact_value|as_list)$"),
        "repeated_logic": "Argument/list splitting and compact-value helpers.",
        "existing_helper_available": True,
        "preferred_existing_helper_or_module": "Reuse Tools.ai.github_evidence_bundle_io.split_path_values/compact_value when the semantics match.",
        "recommendation_type": "reuse_existing_helper",
        "risk": "medium",
        "schema_or_cli_impact": "possible subtle CLI behavior changes; validate with broker/orchestrator smoke tests.",
    },
    {
        "candidate_id": "dup_line_count_helpers",
        "name_pattern": re.compile(r"^(line_count|load_line_counts|count_lines)$"),
        "repeated_logic": "Line-count calculation/loading helper patterns.",
        "existing_helper_available": True,
        "preferred_existing_helper_or_module": "Tools.validation.build_python_line_count_csv is the authoritative generator; use report CSV/JSON outputs instead of re-counting when possible.",
        "recommendation_type": "reuse_existing_helper",
        "risk": "low",
        "schema_or_cli_impact": "none if CSV schema remains File/Lines.",
    },
    {
        "candidate_id": "dup_artifact_chunk_helpers",
        "name_pattern": re.compile(r"^(summarize_artifact|build_included_artifact|discover_related_artifacts|build_included_artifacts|build_artifact_chunk_index|chunk_file_lines)$"),
        "repeated_logic": "Artifact discovery, inclusion and large-file chunk pointer logic.",
        "existing_helper_available": True,
        "preferred_existing_helper_or_module": "Tools.ai.github_evidence_bundle_artifacts.",
        "recommendation_type": "reuse_existing_helper",
        "risk": "medium",
        "schema_or_cli_impact": "must preserve bundle schema fields and chunk pointer metadata.",
    },
    {
        "candidate_id": "dup_tool_request_packet_logic",
        "name_pattern": re.compile(r"^(tool_request|build_.*tool_requests|execute_tool_request|extract_tool_requests|run_.*runtime_tool_broker.*)$"),
        "repeated_logic": "Runtime tool-request packet construction, extraction and broker execution summaries.",
        "existing_helper_available": False,
        "preferred_existing_helper_or_module": "Advisory: consider a future small request-packet helper only after broker/orchestrator schemas stabilize.",
        "recommendation_type": "advisory_only",
        "risk": "medium",
        "schema_or_cli_impact": "possible broker/orchestrator schema impact; do not refactor automatically.",
    },
)

LINE_COUNT_SHARED_DELEGATION_TOKENS = (
    "physical_line_count(",
    "count_file_lines(",
    "parse_line_count_csv_row(",
    "load_line_count_csv_map(",
    "line_count_for_path(",
    "shared_line_count_for_path(",
)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def split_values(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            normalized = part.strip().strip("'\"")
            if normalized and normalized not in out:
                out.append(normalized)
    return out


def safe_id(value: str, fallback: str = "dup_candidate") -> str:
    text = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return text[:100] or fallback


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), None
        except Exception as exc:  # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}"



def iter_python_files(repo_root: Path, roots: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_root in roots:
        root = resolve_path(repo_root, raw_root)
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".py":
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel_parts = set(path.relative_to(repo_root).parts) if path.is_relative_to(repo_root) else set(path.parts)
            if any(part in rel_parts for part in DEFAULT_EXCLUDE_PARTS):
                continue
            files.append(path)
    unique: dict[str, Path] = {}
    for path in files:
        unique[path.resolve(strict=False).as_posix()] = path
    return sorted(unique.values(), key=lambda item: repo_rel(item, repo_root).lower())


def collect_functions(repo_root: Path, files: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    functions: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in files:
        text, error = read_text(path)
        if error:
            warnings.append(f"{repo_rel(path, repo_root)}: {error}")
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            warnings.append(f"{repo_rel(path, repo_root)}: SyntaxError line {exc.lineno}: {exc.msg}")
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            body = "\n".join(lines[max(start - 1, 0): min(end, len(lines))])
            functions.append(
                {
                    "name": node.name,
                    "path": repo_rel(path, repo_root),
                    "line_start": start,
                    "line_end": end,
                    "line_count": max(1, end - start + 1),
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "body_hash_seed": re.sub(r"\s+", " ", body.strip())[:500],
                    "uses_shared_line_count_helper": any(token in body for token in LINE_COUNT_SHARED_DELEGATION_TOKENS),
                }
            )
    return functions, warnings


def files_involved(items: list[dict[str, Any]], limit: int = 16) -> list[str]:
    values = [f"{item['path']}#L{item['line_start']}-L{item['line_end']}" for item in items]
    return values[:limit]


def build_rule_candidates(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for rule in HELPER_RULES:
        matched = [item for item in functions if rule["name_pattern"].match(str(item["name"]))]
        if rule["candidate_id"] == "dup_line_count_helpers":
            matched = [item for item in matched if not item.get("uses_shared_line_count_helper")]
        distinct_files = sorted({str(item["path"]) for item in matched})
        if len(matched) < 2 or len(distinct_files) < 2:
            continue
        candidate_id = str(rule["candidate_id"])
        candidates.append(
            {
                "candidate_id": candidate_id,
                "repeated_logic": rule["repeated_logic"],
                "files_involved": files_involved(matched),
                "function_names": sorted({str(item["name"]) for item in matched}),
                "occurrence_count": len(matched),
                "distinct_file_count": len(distinct_files),
                "existing_helper_available": bool(rule["existing_helper_available"]),
                "preferred_existing_helper_or_module": rule["preferred_existing_helper_or_module"],
                "recommendation_type": rule["recommendation_type"],
                "risk": rule["risk"],
                "schema_or_cli_impact": rule["schema_or_cli_impact"],
                "validation_required": validation_for_candidate(candidate_id),
                "manual_review_required": True,
            }
        )
    return candidates


def build_exact_name_candidates(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in functions:
        name = str(item["name"])
        if name.startswith("_"):
            continue
        by_name[name].append(item)
    candidates: list[dict[str, Any]] = []
    helper_rule_ids = {str(rule["candidate_id"]) for rule in HELPER_RULES}
    for name, items in sorted(by_name.items()):
        distinct_files = sorted({str(item["path"]) for item in items})
        if len(items) < 2 or len(distinct_files) < 2:
            continue
        if any(rule["name_pattern"].match(name) for rule in HELPER_RULES):
            continue
        candidate_id = safe_id(f"dup_function_{name}")
        if candidate_id in helper_rule_ids:
            continue
        recommendation = "needs_more_context"
        preferred = "Review whether same-name helper semantics are intentionally local before extracting."
        risk = "medium"
        if name in {"main", "parse_args"}:
            recommendation = "keep_local_by_design"
            preferred = "CLI entrypoints should generally remain local."
            risk = "low"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "repeated_logic": f"Same public function name appears in multiple files: {name}",
                "files_involved": files_involved(items),
                "function_names": [name],
                "occurrence_count": len(items),
                "distinct_file_count": len(distinct_files),
                "existing_helper_available": False,
                "preferred_existing_helper_or_module": preferred,
                "recommendation_type": recommendation,
                "risk": risk,
                "schema_or_cli_impact": "unknown until bodies are compared; manual review required.",
                "validation_required": ["python -m py_compile touched files", "check_python_syntax"],
                "manual_review_required": True,
            }
        )
    return candidates


def validation_for_candidate(candidate_id: str) -> list[str]:
    if "tool_request" in candidate_id:
        return [
            "python Tools/validation/run_agent_runtime_tool_broker_smoke.py --repo-root .",
            "python Tools/validation/run_orchestrator_gpu_runtime_tool_routing_smoke.py --repo-root .",
            "python Tools/validation/run_npu_runtime_tool_execution_smoke.py --repo-root .",
        ]
    if "artifact" in candidate_id or "chunk" in candidate_id:
        return [
            "python Tools/validation/run_shared_toolbox_ai_to_ai_bundle_smoke.py --repo-root .",
            "python -m Tools.validation.check_github_evidence_bundle --repo-root . --bundle <bundle>",
        ]
    return ["python -m py_compile touched files", "python -m Tools.validation.check_python_syntax --repo-root ."]


def collect_report_status(repo_root: Path, report_paths: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    for raw in report_paths:
        path = resolve_path(repo_root, raw)
        data = read_json_report(path)
        item = {
            "path": repo_rel(path, repo_root),
            "exists": path.exists(),
            "kind": data.get("kind"),
            "passed": data.get("passed"),
            "provider_execution_performed": data.get("provider_execution_performed"),
            "patch_application_performed": data.get("patch_application_performed"),
            "sqlite_write_performed": data.get("sqlite_write_performed"),
            "persistent_memory_write_performed": data.get("persistent_memory_write_performed"),
            "errors": data.get("errors", []),
            "warnings": data.get("warnings", []),
        }
        if path.exists() and not data:
            warnings.append(f"{repo_rel(path, repo_root)} exists but is not a JSON object or could not be parsed")
        reports.append(item)
    return reports, warnings


def verify_layering(repo_root: Path) -> dict[str, Any]:
    files = {
        "builder": repo_root / "Tools/ai/build_shared_toolbox_ai_to_ai_bundle.py",
        "bundle": repo_root / "Tools/ai/build_github_evidence_bundle.py",
        "artifacts": repo_root / "Tools/ai/github_evidence_bundle_artifacts.py",
        "validator": repo_root / "Tools/validation/check_github_evidence_bundle.py",
        "smoke": repo_root / "Tools/validation/run_shared_toolbox_ai_to_ai_bundle_smoke.py",
    }
    content = {key: read_text(path)[0] for key, path in files.items()}
    checks = {
        "layering_preserved": all(path.exists() for path in files.values()),
        "builder_delegates_to_common_bundle": "build_bundle" in content["builder"] and "Tools.ai.build_github_evidence_bundle" in content["builder"],
        "chunking_in_common_evidence_layer": "artifact_chunk_index" in content["artifacts"] or "build_artifact_chunk_index" in content["artifacts"],
        "validator_reused": "validate_github_evidence_bundles" in content["builder"] and "check_github_evidence_bundle" in content["builder"],
        "smoke_coverage_present": all(token in content["smoke"] for token in ("chunked_large_files_seen", "bundle_validation_passed", "recursive_default_files_seen")),
        "cli_schema_preserved": "parse_args" in content["builder"] and "--validate-bundle" in content["builder"],
        "report_schema_preserved": "shared_toolbox_ai_to_ai_final_summary" in content["builder"] and "github_validation_evidence_bundle" in content["bundle"],
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def audit_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = data.get(key)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def normalize_imported_candidate(item: dict[str, Any], *, source: str, index: int) -> dict[str, Any]:
    candidate = dict(item)
    fallback = candidate.get("candidate_id") or candidate.get("id") or candidate.get("title") or candidate.get("repeated_logic")
    candidate["candidate_id"] = safe_id(str(fallback or f"imported_audit_candidate_{index:03d}"))
    candidate.setdefault("source", source)
    candidate.setdefault("repeated_logic", candidate.get("title") or "Imported local-AI/refactor audit candidate.")
    candidate.setdefault("files_involved", candidate.get("target_files") or [])
    candidate.setdefault("existing_helper_available", None)
    candidate.setdefault("preferred_existing_helper_or_module", candidate.get("preferred_helper") or candidate.get("preferred_existing_helper_or_module") or "Imported audit did not specify a helper/module.")
    candidate.setdefault("recommendation_type", candidate.get("recommendation_type") or "needs_more_context")
    candidate.setdefault("risk", candidate.get("risk") or "needs_review")
    candidate.setdefault("schema_or_cli_impact", candidate.get("schema_or_cli_impact") or "needs manual review")
    candidate.setdefault("validation_required", candidate.get("validation") or ["manual review", "check_python_syntax"])
    candidate.setdefault("manual_review_required", True)
    return candidate


def merge_existing_audit_candidates(repo_root: Path, paths: list[str]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    candidate_keys = (
        "duplication_candidates",
        "refactor_candidates",
        "duplicate_code_candidates",
        "helper_reuse_candidates",
        "manual_review_patch_plan_candidates",
    )
    for raw in paths:
        path = resolve_path(repo_root, raw)
        source = repo_rel(path, repo_root)
        data = read_json_report(path)
        if not data:
            continue
        index = 0
        for key in candidate_keys:
            for item in audit_list(data, key):
                index += 1
                candidate = normalize_imported_candidate(item, source=source, index=index)
                candidate.setdefault("imported_from_key", key)
                merged.append(candidate)
    return merged


def summarize_existing_audit_reports(repo_root: Path, paths: list[str]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    helper_recommendations: list[str] = []
    advisory_findings: list[str] = []
    manual_plans: list[dict[str, Any]] = []
    for raw in paths:
        path = resolve_path(repo_root, raw)
        rel = repo_rel(path, repo_root)
        data = read_json_report(path)
        summary = {
            "path": rel,
            "exists": path.exists(),
            "kind": data.get("kind") if data else None,
            "passed": data.get("passed") if data else None,
            "provider_execution_performed": data.get("provider_execution_performed") if data else None,
            "patch_application_performed": data.get("patch_application_performed") if data else None,
            "sqlite_write_performed": data.get("sqlite_write_performed") if data else None,
            "persistent_memory_write_performed": data.get("persistent_memory_write_performed") if data else None,
            "duplication_candidate_count": len(audit_list(data, "duplication_candidates")) if data else 0,
            "manual_review_patch_plan_candidate_count": len(audit_list(data, "manual_review_patch_plan_candidates")) if data else 0,
        }
        summaries.append(summary)
        if not data:
            continue
        raw_helper = data.get("helper_reuse_recommendations")
        if isinstance(raw_helper, list):
            for item in raw_helper:
                text = str(item).strip()
                if text and text not in helper_recommendations:
                    helper_recommendations.append(text)
        raw_advisory = data.get("advisory_only_findings")
        if isinstance(raw_advisory, list):
            for item in raw_advisory:
                text = str(item).strip()
                if text and text not in advisory_findings:
                    advisory_findings.append(text)
        for item in audit_list(data, "manual_review_patch_plan_candidates"):
            plan = dict(item)
            plan.setdefault("source", rel)
            plan.setdefault("manual_review_required", True)
            manual_plans.append(plan)
    return {
        "reports": summaries,
        "helper_reuse_recommendations": helper_recommendations,
        "advisory_only_findings": advisory_findings,
        "manual_review_patch_plan_candidates": manual_plans,
    }


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = str(item.get("candidate_id") or item.get("repeated_logic") or len(deduped))
        if key not in deduped:
            deduped[key] = item
            continue
        current = deduped[key]
        current_files = list(current.get("files_involved") or [])
        for path in item.get("files_involved") or []:
            if path not in current_files:
                current_files.append(path)
        current["files_involved"] = current_files[:20]
        current["occurrence_count"] = max(int(current.get("occurrence_count") or 0), int(item.get("occurrence_count") or 0))
    return list(deduped.values())


def build_manual_review_patch_plan_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for item in candidates:
        if item.get("recommendation_type") not in {"reuse_existing_helper", "promote_existing_function"}:
            continue
        if item.get("risk") not in {"low", "medium"}:
            continue
        plans.append(
            {
                "candidate_id": f"patch_plan_{item.get('candidate_id')}",
                "title": f"Manual-review refactor for {item.get('candidate_id')}",
                "recommendation_type": "ready_for_patch_plan" if item.get("risk") == "low" else "needs_more_context",
                "source_candidate_id": item.get("candidate_id"),
                "target_files": sorted({str(value).split("#L", 1)[0] for value in item.get("files_involved", [])})[:8],
                "preferred_existing_helper_or_module": item.get("preferred_existing_helper_or_module"),
                "validation": item.get("validation_required", []),
                "manual_review_required": True,
            }
        )
    return plans[:8]


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Refactor Duplication Audit", ""]
    for key in (
        "stamp",
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "python_file_count",
        "function_count",
        "duplication_candidate_count",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Refactor verification")
    lines.append("")
    for key, value in report.get("refactor_verification", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Duplication candidates")
    lines.append("")
    for item in report.get("duplication_candidates", []):
        lines.append(f"### `{item.get('candidate_id')}`")
        lines.append("")
        lines.append(f"- repeated_logic: {item.get('repeated_logic')}")
        lines.append(f"- recommendation_type: `{item.get('recommendation_type')}`")
        lines.append(f"- risk: `{item.get('risk')}`")
        lines.append(f"- preferred helper/module: {item.get('preferred_existing_helper_or_module')}")
        lines.append(f"- occurrence_count: `{item.get('occurrence_count')}`")
        lines.append("- files:")
        for value in item.get("files_involved", [])[:10]:
            lines.append(f"  - `{value}`")
        lines.append("")
    lines.append("## Manual-review patch-plan candidates")
    lines.append("")
    if report.get("manual_review_patch_plan_candidates"):
        for item in report.get("manual_review_patch_plan_candidates", []):
            lines.append(f"- `{item.get('candidate_id')}`: {item.get('title')} ({item.get('recommendation_type')})")
    else:
        lines.append("- No ready manual-review patch-plan candidate was selected.")
    lines.append("")
    lines.append("## Advisory-only findings")
    lines.append("")
    for value in report.get("advisory_only_findings", []):
        lines.append(f"- {value}")
    lines.append("")
    if report.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        for value in report.get("warnings", []):
            lines.append(f"- {value}")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for value in report.get("errors", []):
            lines.append(f"- {value}")
    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    stamp = args.stamp or now_stamp()
    roots = split_values(args.root) or list(DEFAULT_ROOTS)
    reports_raw = split_values(args.report)
    reports_raw.extend(split_values(args.line_count_report))
    reports_raw.extend(split_values(args.code_interpreter_report))
    reports_raw.extend(split_values(args.python_syntax_report))
    reports_raw.extend(split_values(args.bundle_smoke_report))
    reports_raw.extend(split_values(args.memory_routing_report))
    report_paths = []
    for value in reports_raw:
        if value not in report_paths:
            report_paths.append(value)
    input_audit_paths = split_values(args.input_audit_report)
    existing_audit_summary = summarize_existing_audit_reports(repo_root, input_audit_paths)

    files = iter_python_files(repo_root, roots)
    functions, parse_warnings = collect_functions(repo_root, files)
    candidates = dedupe_candidates(
        build_rule_candidates(functions)
        + build_exact_name_candidates(functions)
        + merge_existing_audit_candidates(repo_root, input_audit_paths)
    )
    candidates = candidates[: max(1, args.max_candidates)]
    refactor_verification = verify_layering(repo_root)
    report_status, report_warnings = collect_report_status(repo_root, report_paths)

    advisory = [
        "Do not apply refactors automatically from this report; generate a focused manual-review patch plan first.",
        "Keep provider/orchestrator request-packet refactors advisory-only until schema stability is proven by broker/orchestrator smoke tests.",
    ]
    if any(item.get("candidate_id") == "dup_markdown_renderers" for item in candidates):
        advisory.append("Markdown rendering duplication is mostly presentation-layer and should remain local unless a stable shared status-section helper emerges.")

    source_failed = [item for item in report_status if item.get("passed") is False]
    errors = [f"source report failed: {item.get('path')}" for item in source_failed]
    warnings = parse_warnings + report_warnings
    if not candidates:
        warnings.append("No duplication candidates detected; verify roots and patterns before treating this as complete.")

    generated_patch_plan_candidates = build_manual_review_patch_plan_candidates(candidates)
    imported_patch_plan_candidates = list(existing_audit_summary.get("manual_review_patch_plan_candidates") or [])
    manual_review_patch_plan_candidates = generated_patch_plan_candidates + imported_patch_plan_candidates
    helper_reuse_recommendations = [
        "Reuse Tools.ai.github_evidence_bundle_io for evidence-bundle path/text/JSON helpers when semantics match.",
        "Reuse Tools.ai.github_evidence_bundle_artifacts for artifact discovery and chunk pointer metadata.",
        "Reuse Tools.validation.report_utils for validation output path resolution and JSON report writing.",
        "Prefer promoting existing local functions into existing helper modules over creating new generic helper modules.",
    ]
    for item in existing_audit_summary.get("helper_reuse_recommendations") or []:
        if item not in helper_reuse_recommendations:
            helper_reuse_recommendations.append(item)
    advisory_only_findings = list(advisory)
    for item in existing_audit_summary.get("advisory_only_findings") or []:
        if item not in advisory_only_findings:
            advisory_only_findings.append(item)

    report = {
        "schema_version": 1,
        "kind": "refactor_duplication_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stamp": stamp,
        "repo_root": str(repo_root),
        "roots": roots,
        "passed": not errors and bool(refactor_verification.get("passed")),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "python_file_count": len(files),
        "function_count": len(functions),
        "duplication_candidate_count": len(candidates),
        "refactor_verification": refactor_verification,
        "duplication_candidates": candidates,
        "helper_reuse_recommendations": helper_reuse_recommendations,
        "manual_review_patch_plan_candidates": manual_review_patch_plan_candidates,
        "advisory_only_findings": advisory_only_findings,
        "input_audit_reports": existing_audit_summary.get("reports", []),
        "source_reports": report_status,
        "validation_commands": [
            "python -m py_compile Tools/ai/build_refactor_duplication_audit.py Tools/validation/run_refactor_duplication_audit_smoke.py",
            "python Tools/validation/run_refactor_duplication_audit_smoke.py --repo-root .",
            "python -m Tools.validation.check_python_syntax --repo-root .",
            "python Tools/validation/run_agent_runtime_tool_broker_smoke.py --repo-root .",
        ],
        "stop_conditions": [
            "Stop if python syntax validation fails.",
            "Stop if patch_application_performed=True.",
            "Stop if sqlite_write_performed=True or persistent_memory_write_performed=True.",
            "Stop if a ready refactor would break CLI/report schema without a migration plan.",
        ],
        "errors": errors,
        "warnings": warnings,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "manual_review_required": True,
        },
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--line-count-report", action="append", default=[])
    parser.add_argument("--code-interpreter-report", action="append", default=[])
    parser.add_argument("--python-syntax-report", action="append", default=[])
    parser.add_argument("--bundle-smoke-report", action="append", default=[])
    parser.add_argument("--memory-routing-report", action="append", default=[])
    parser.add_argument("--input-audit-report", action="append", default=[])
    parser.add_argument("--max-candidates", type=int, default=40)
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown-output", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    stamp = args.stamp or now_stamp()
    if not args.stamp:
        args.stamp = stamp
    output = resolve_output_path(repo_root, args.output or f"output/analysis/refactor_duplication_audit_{stamp}.json")
    markdown = resolve_output_path(repo_root, args.markdown_output or f"output/analysis/refactor_duplication_audit_{stamp}.md")
    report = build_report(args)
    write_json_report(report, output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "python_file_count": report["python_file_count"],
                "function_count": report["function_count"],
                "duplication_candidate_count": report["duplication_candidate_count"],
                "manual_review_patch_plan_candidate_count": len(report["manual_review_patch_plan_candidates"]),
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
