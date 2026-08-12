#!/usr/bin/env python3
"""Build shared-toolbox AI-to-AI final summaries and compact evidence bundles.

Report-only builder for issue #141. It assembles a final summary from existing
reports, delegates compact bundle construction to the common GitHub evidence
bundle builder, and optionally validates the resulting bundle.

The tool itself does not execute providers, apply patches, run Blender, or write
SQLite/persistent memory.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.agent_runtime_tool_broker import TOOL_SPECS
    from Tools.ai.build_github_evidence_bundle import build_bundle
    from Tools.ai.github_evidence_bundle_artifacts import DEFAULT_CHUNK_LINES, DEFAULT_RECURSIVE_MAX_FILES
    from Tools.ai.github_evidence_bundle_io import read_json, read_text, repo_relative, resolve_repo_path, split_path_values
    from Tools.validation.check_github_evidence_bundle import validate_github_evidence_bundles
    from Tools.validation.report_utils import resolve_output_path, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.agent_runtime_tool_broker import TOOL_SPECS
    from Tools.ai.build_github_evidence_bundle import build_bundle
    from Tools.ai.github_evidence_bundle_artifacts import DEFAULT_CHUNK_LINES, DEFAULT_RECURSIVE_MAX_FILES
    from Tools.ai.github_evidence_bundle_io import read_json, read_text, repo_relative, resolve_repo_path, split_path_values
    from Tools.validation.check_github_evidence_bundle import validate_github_evidence_bundles
    from Tools.validation.report_utils import resolve_output_path, write_json_report


DEFAULT_STAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_BASENAME_PREFIX = "shared_toolbox_ai_to_ai_bundle"
DEFAULT_FINAL_SUMMARY_PREFIX = "shared_toolbox_ai_to_ai_final_summary"
DEFAULT_RECURSIVE_REPORT_ROOTS: tuple[str, ...] = (
    "output/validation",
    "output/analysis",
    "output/ai_pipeline",
)
DEFAULT_RECURSIVE_ARTIFACT_ROOTS: tuple[str, ...] = (
    "output/analysis",
    "output/ai_pipeline",
    "docs/LOCAL_AI_TASKS",
)

DEFAULT_REPORT_TEMPLATES: tuple[str, ...] = (
    "output/validation/shared_toolbox_python_syntax_{stamp}.json",
    "output/analysis/shared_toolbox_code_interpreter_{stamp}.json",
    "output/validation/shared_toolbox_gpu_contract_smoke_{stamp}.json",
    "output/validation/shared_toolbox_gpu_routing_{stamp}.json",
    "output/validation/shared_toolbox_npu_execution_{stamp}.json",
    "output/validation/shared_toolbox_npu_contract_{stamp}.json",
    "output/validation/npu_provider_environment_shared_toolbox_{stamp}.json",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_orchestrator.json",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_gpu.json",
    "output/analysis/shared_toolbox_gpu_npu_sync_{stamp}.json",
    "output/analysis/shared_toolbox_gpu_contract_replay_{stamp}.json",
)

FULL_TOOLBOX_REPORT_TEMPLATES: tuple[str, ...] = (
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_integrated.json",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_workflow.json",
    "output/validation/agent_review_warning_policy_{stamp}.json",
    "output/ai_pipeline/full_toolbox_{stamp}_agent_review_decision_loop.json",
    "output/patch_specs/full_toolbox_{stamp}_agent_review_patch_plan.json",
    "output/ai_pipeline/full_toolbox_{stamp}_deterministic_recommendations.json",
    "output/ai_pipeline/full_toolbox_{stamp}_bridge_orchestrator.json",
    "output/ai_pipeline/full_toolbox_{stamp}_orchestrator.json",
    "output/ai_pipeline/full_toolbox_{stamp}_parallel_gpu.json",
    "output/validation/local_provider_probe.json",
    "output/validation/ai_workload_report_quality.json",
    "output/analysis/repository_consistency_map_full_toolbox_{stamp}.json",
    "output/validation/repository_consistency_map_smoke_full_toolbox_{stamp}.json",
    "output/analysis/code_interpreter_full_toolbox_{stamp}.json",
    "output/validation/python_line_count_full_toolbox_{stamp}.json",
    "output/validation/python_syntax_full_toolbox_{stamp}.json",
    "output/validation/gpu_planner_json_contract_smoke_full_toolbox_{stamp}.json",
    "output/validation/deterministic_recommendation_synthesizer_smoke_full_toolbox_{stamp}.json",
    "output/validation/agent_review_decision_loop_smoke_full_toolbox_{stamp}.json",
    "output/validation/npu_provider_environment_full_toolbox_{stamp}.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_run_telemetry_summary_{stamp}.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_usage_telemetry_{stamp}.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest_{stamp}.json",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_{stamp}_cloud_semantic_deterministic_chunk_manifest.json",
)

FULL_TOOLBOX_ARTIFACT_TEMPLATES: tuple[str, ...] = (
    "output/patch_specs/full_toolbox_{stamp}_agent_review_patch_plan.md",
    "output/ai_pipeline/full_toolbox_{stamp}_agent_review_decision_loop.md",
    "output/ai_pipeline/full_toolbox_{stamp}_deterministic_recommendations.md",
    "output/ai_pipeline/full_toolbox_{stamp}_orchestrator.md",
    "output/ai_pipeline/full_toolbox_{stamp}_parallel_gpu.md",
    "output/analysis/repository_consistency_map_full_toolbox_{stamp}.md",
    "output/validation/repository_consistency_map_smoke_full_toolbox_{stamp}.md",
    "output/analysis/code_interpreter_full_toolbox_{stamp}.md",
    "output/validation/python_line_count_full_toolbox_{stamp}.md",
    "output/validation/python_line_count_all_python_files_{stamp}.md",
    "output/validation/gpu_planner_json_contract_smoke_full_toolbox_{stamp}.md",
    "output/validation/deterministic_recommendation_synthesizer_smoke_full_toolbox_{stamp}.md",
    "output/validation/agent_review_decision_loop_smoke_full_toolbox_{stamp}.md",
    "output/validation/npu_provider_environment_full_toolbox_{stamp}.md",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_integrated.md",
    "output/validation/agent_review_full_toolbox_decision_loop_{stamp}_workflow.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_run_telemetry_summary_{stamp}.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_usage_telemetry_{stamp}.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest_{stamp}.md",
    "docs/LOCAL_VALIDATION_EVIDENCE/full_toolbox_{stamp}_cloud_semantic_deterministic_chunk_manifest.md",
)

DEFAULT_ARTIFACT_TEMPLATES: tuple[str, ...] = (
    "docs/LOCAL_AI_TASKS/shared-runtime-toolbox-ai-to-ai-next-task-2026-05-03.md",
    "docs/LOCAL_AI_TASKS/shared-runtime-toolbox-orchestration-architecture.md",
    "output/analysis/shared_toolbox_code_interpreter_{stamp}.md",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_orchestrator.md",
    "output/ai_pipeline/shared_toolbox_ai_to_ai_{stamp}_gpu.md",
    "output/analysis/shared_toolbox_gpu_npu_sync_{stamp}.md",
    "output/analysis/shared_toolbox_gpu_contract_replay_{stamp}.md",
    "output/analysis/shared_toolbox_ai_to_ai_final_summary_{stamp}.md",
)


def runtime_tool_capabilities() -> list[dict[str, Any]]:
    """Build tool capability rows from the broker allowlist, not a duplicate list."""
    rows: list[dict[str, Any]] = []
    for name in sorted(TOOL_SPECS):
        spec = TOOL_SPECS[name]
        rows.append(
            {
                "tool_name": spec.name,
                "category": classify_tool_category(spec.name),
                "safe_default_mode": "report-only" if spec.name != "runtime_sqlite_memory" else "controlled read-only/status by default",
                "what_it_can_do": [spec.description],
                "what_it_must_not_do": tool_must_not_do(spec.name),
                "recommended_next_use": recommended_tool_use(spec.name),
                "allowed_args": list(spec.allowed_args),
            }
        )
    return rows


def classify_tool_category(tool_name: str) -> str:
    if "inventory" in tool_name or "line_count" in tool_name:
        return "inventory"
    if tool_name.startswith("check_") or tool_name.endswith("_smoke"):
        return "validation"
    if "context" in tool_name:
        return "context"
    if "sqlite" in tool_name or "memory" in tool_name:
        return "memory_status"
    if "code_interpreter" in tool_name:
        return "static_analysis"
    return "support_tool"


def tool_must_not_do(tool_name: str) -> list[str]:
    base = ["execute arbitrary shell commands", "apply patches", "run Blender runtime", "commit output artifacts"]
    if tool_name == "runtime_sqlite_memory":
        base.append("write persistent memory without explicit confirmation and authorization")
    else:
        base.append("write SQLite or persistent memory")
    return base


def recommended_tool_use(tool_name: str) -> str:
    mapping = {
        "build_python_line_count_csv": "Refresh complete Python inventory before refactor planning.",
        "build_agent_memory_inventory": "Summarize durable project memory as read-only context.",
        "build_agent_agnostic_tool_inventory": "Discover reusable tooling before adding new scripts.",
        "build_agent_transient_request_context": "Assemble request-scoped context for local AI planning.",
        "check_python_syntax": "Gate Python source changes.",
        "check_validation_report_contract": "Gate report quality before evidence bundling.",
        "run_gpu_planner_json_contract_smoke": "Validate planner JSON contract without providers.",
        "build_code_interpreter_report": "Build static analysis/refactor evidence.",
        "runtime_sqlite_memory": "Read memory status/search through broker-controlled actions.",
    }
    return mapping.get(tool_name, "Use through the runtime tool broker when a report-only request requires it.")


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON object while reusing shared evidence-bundle IO helpers."""
    data = read_json(path)
    if data is not None:
        return data, None
    if not path.exists():
        return None, "missing"
    text, read_error = read_text(path)
    if read_error:
        return None, read_error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    if not isinstance(parsed, dict):
        return None, f"expected JSON object, got {type(parsed).__name__}"
    return parsed, None


def existing_paths(repo_root: Path, raw_paths: list[str], *, label: str, include_missing_optional: bool) -> tuple[list[str], list[dict[str, Any]]]:
    present: list[str] = []
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_paths:
        path = resolve_repo_path(repo_root, raw)
        rel = repo_relative(path, repo_root)
        if rel in seen:
            continue
        seen.add(rel)
        if path.exists():
            present.append(rel)
        else:
            missing.append({"path": rel, "reason": f"optional {label} missing"})
            if include_missing_optional:
                present.append(rel)
    return present, missing


def report_templates_for_stamp(stamp: str) -> list[str]:
    templates = list(DEFAULT_REPORT_TEMPLATES) + list(FULL_TOOLBOX_REPORT_TEMPLATES)
    return [item.format(stamp=stamp) for item in templates]


def artifact_templates_for_stamp(stamp: str) -> list[str]:
    templates = list(DEFAULT_ARTIFACT_TEMPLATES) + list(FULL_TOOLBOX_ARTIFACT_TEMPLATES)
    return [item.format(stamp=stamp) for item in templates]


def coalesce_list(*values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for items in values:
        for item in split_path_values(items):
            if item not in seen:
                result.append(item)
                seen.add(item)
    return result


def collect_report_facts(repo_root: Path, report_paths: list[str]) -> dict[str, Any]:
    reports_generated: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    provider_execution_performed = False
    patch_application_performed = False
    source_writes_performed = False
    sqlite_write_performed = False
    persistent_memory_write_performed = False
    blender_runtime_execution_performed = False
    tool_requests: list[dict[str, Any]] = []

    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        entry: dict[str, Any] = {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": data is not None,
            "kind": data.get("kind") if data else None,
            "passed": data.get("passed") if data else None,
        }
        if parse_error and parse_error != "missing":
            entry["parse_error"] = parse_error
            warnings.append(f"{entry['path']}: {parse_error}")
        if data:
            provider_execution_performed = provider_execution_performed or data.get("provider_execution_performed") is True
            patch_application_performed = patch_application_performed or data.get("patch_application_performed") is True
            source_writes_performed = source_writes_performed or data.get("source_writes_performed") is True
            sqlite_write_performed = sqlite_write_performed or data.get("sqlite_write_performed") is True
            persistent_memory_write_performed = persistent_memory_write_performed or data.get("persistent_memory_write_performed") is True
            blender_runtime_execution_performed = blender_runtime_execution_performed or data.get("blender_runtime_execution_performed") is True
            if isinstance(data.get("errors"), list):
                errors.extend(str(item) for item in data.get("errors", []) if item)
            if isinstance(data.get("warnings"), list):
                warnings.extend(str(item) for item in data.get("warnings", []) if item)
            for key in ("tool_requests", "runtime_tool_requests"):
                raw = data.get(key)
                if isinstance(raw, list):
                    for request in raw:
                        if isinstance(request, dict):
                            tool_requests.append(
                                {
                                    "source_report": repo_relative(path, repo_root),
                                    "id": request.get("id"),
                                    "tool": request.get("tool"),
                                    "reason": request.get("reason"),
                                    "args": request.get("args") if isinstance(request.get("args"), dict) else {},
                                }
                            )
        reports_generated.append(entry)

    return {
        "reports_generated": reports_generated,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": provider_execution_performed,
        "patch_application_performed": patch_application_performed,
        "source_writes_performed": source_writes_performed,
        "sqlite_write_performed": sqlite_write_performed,
        "persistent_memory_write_performed": persistent_memory_write_performed,
        "blender_runtime_execution_performed": blender_runtime_execution_performed,
        "tool_requests_executed_or_proposed": tool_requests,
    }


def default_tool_requests() -> list[dict[str, Any]]:
    return [
        {
            "id": f"request_{name}",
            "tool": name,
            "reason": recommended_tool_use(name),
            "args": {},
            "status": "proposed_or_reported",
        }
        for name in sorted(TOOL_SPECS)
        if name in {"check_python_syntax", "check_validation_report_contract", "build_code_interpreter_report"}
    ]


def build_remaining_gaps(
    missing_reports: list[dict[str, Any]],
    missing_artifacts: list[dict[str, Any]],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    gaps.extend(missing_reports)
    gaps.extend(missing_artifacts)
    if not any(item.get("tool") for item in facts.get("tool_requests_executed_or_proposed", [])):
        gaps.append(
            {
                "gap": "runtime tool requests not proven in provider-backed run",
                "detail": "No concrete tool_requests were found in the included reports.",
            }
        )
    if facts.get("patch_application_performed"):
        gaps.append({"gap": "patch application detected", "detail": "Expected report-only execution."})
    if facts.get("sqlite_write_performed") or facts.get("persistent_memory_write_performed"):
        gaps.append({"gap": "SQLite or persistent memory write detected", "detail": "Expected read-only/report-only behavior."})
    return gaps


def extract_full_run_patch_plan_summary(repo_root: Path, report_paths: list[str]) -> dict[str, Any]:
    # Promote full-run patch-plan summary into the production bundle final summary.
    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        if parse_error or not data:
            continue
        if data.get("kind") != "agent_review_patch_plan":
            continue
        raw_summary = data.get("patch_plan_summary")
        summary_items = raw_summary if isinstance(raw_summary, list) else []
        return {
            "seen": True,
            "source": repo_relative(path, repo_root),
            "passed": data.get("passed"),
            "patch_plan_count": data.get("patch_plan_count") or len(summary_items),
            "fallback_used": data.get("fallback_used"),
            "manual_review_required": data.get("manual_review_required"),
            "provider_execution_performed": data.get("provider_execution_performed"),
            "patch_application_performed": data.get("patch_application_performed"),
            "source_writes_performed": data.get("source_writes_performed"),
            "summary_count": len(summary_items),
            "top_items": summary_items[:20],
            "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
            "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
        }
    return {
        "seen": False,
        "source": "",
        "patch_plan_count": 0,
        "summary_count": 0,
        "top_items": [],
        "warnings": [],
        "errors": ["full-run patch plan report not found in production bundle inputs"],
    }


def extract_provider_diagnostics_summary(repo_root: Path, report_paths: list[str]) -> dict[str, Any]:
    # Summarize provider/GPU/NPU diagnostics without hiding recovered failures.
    diagnostics: list[dict[str, Any]] = []
    provider_execution_seen = False
    gpu_primary_advisory_succeeded = False
    deterministic_recovery_used = False

    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        if parse_error or not data:
            continue

        kind = str(data.get("kind") or "")
        passed = data.get("passed")
        provider_execution_seen = provider_execution_seen or data.get("provider_execution_performed") is True

        if kind in {
            "agent_gpu_npu_parallel_orchestrator",
            "agent_gpu_parallel_report",
            "local_provider_probe",
            "ai_workload_report_quality",
        }:
            errors = data.get("errors") if isinstance(data.get("errors"), list) else []
            warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
            diagnostics.append(
                {
                    "path": repo_relative(path, repo_root),
                    "kind": kind,
                    "passed": passed,
                    "provider_execution_requested": data.get("provider_execution_requested"),
                    "provider_execution_performed": data.get("provider_execution_performed"),
                    "classification": data.get("classification"),
                    "provider_error": data.get("provider_error"),
                    "recommendation_count": data.get("recommendation_count"),
                    "errors": errors[:20],
                    "warnings": warnings[:20],
                }
            )
            if kind == "agent_gpu_parallel_report" and passed is True and int(data.get("recommendation_count") or 0) > 0:
                gpu_primary_advisory_succeeded = True

        if kind in {
            "deterministic_recommendation_synthesizer",
            "agent_review_decision_loop",
            "agent_review_patch_plan",
        } and passed is True:
            if int(data.get("recommendation_count") or 0) > 0 or int(data.get("patch_plan_count") or 0) > 0:
                deterministic_recovery_used = True

    provider_failure_detected = any(item.get("passed") is False for item in diagnostics)
    return {
        "provider_execution_seen": provider_execution_seen,
        "gpu_primary_advisory_succeeded": gpu_primary_advisory_succeeded,
        "provider_failure_detected": provider_failure_detected,
        "deterministic_recovery_used": deterministic_recovery_used,
        "diagnostics": diagnostics,
        **classify_provider_advisory_state({
            "provider_execution_seen": provider_execution_seen,
            "gpu_primary_advisory_succeeded": gpu_primary_advisory_succeeded,
            "provider_failure_detected": provider_failure_detected,
            "deterministic_recovery_used": deterministic_recovery_used,
            "diagnostics": diagnostics,
        }),
    }


def classify_provider_advisory_state(provider_diagnostics: dict[str, Any]) -> dict[str, Any]:
    # Classify provider state without hiding recovered/degraded runs.
    diagnostics = provider_diagnostics.get("diagnostics") if isinstance(provider_diagnostics, dict) else []
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    failure_reasons: list[str] = []
    degraded_components: list[str] = []

    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        kind = str(item.get("kind") or "")
        passed = item.get("passed")
        errors = item.get("errors") if isinstance(item.get("errors"), list) else []
        provider_error = item.get("provider_error")

        if passed is False:
            degraded_components.append(path or kind or "provider_report")
        if provider_error:
            failure_reasons.append(f"{path or kind}: {provider_error}")
        for error in errors[:5]:
            if error:
                failure_reasons.append(f"{path or kind}: {error}")

    gpu_ok = bool(provider_diagnostics.get("gpu_primary_advisory_succeeded"))
    provider_seen = bool(provider_diagnostics.get("provider_execution_seen"))
    failure_seen = bool(provider_diagnostics.get("provider_failure_detected"))
    recovered = bool(provider_diagnostics.get("deterministic_recovery_used"))

    if gpu_ok:
        state = "primary_gpu_advisory_succeeded"
    elif provider_seen and failure_seen and recovered:
        state = "recovered_degraded_provider"
    elif provider_seen and failure_seen:
        state = "provider_failed_without_recovery"
    elif provider_seen:
        state = "provider_seen_without_primary_gpu_advisory"
    else:
        state = "provider_not_seen"

    return {
        "provider_advisory_state": state,
        "provider_failure_reasons": failure_reasons[:20],
        "degraded_provider_components": degraded_components[:20],
    }

def build_final_summary(
    *,
    repo_root: Path,
    stamp: str,
    report_paths: list[str],
    artifact_paths: list[str],
    bundle_paths: list[str],
    recommended_next_task_md: str,
    missing_reports: list[dict[str, Any]],
    missing_artifacts: list[dict[str, Any]],
    recursive_defaults: dict[str, Any] | None = None,
    chunked_file_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    facts = collect_report_facts(repo_root, report_paths)
    patch_plan_summary = extract_full_run_patch_plan_summary(repo_root, report_paths)
    provider_diagnostics = extract_provider_diagnostics_summary(repo_root, report_paths)
    tool_capabilities = runtime_tool_capabilities()
    tool_requests = facts.get("tool_requests_executed_or_proposed") or default_tool_requests()
    remaining_gaps = build_remaining_gaps(missing_reports, missing_artifacts, facts)
    passed = not (
        facts.get("patch_application_performed")
        or facts.get("sqlite_write_performed")
        or facts.get("persistent_memory_write_performed")
        or facts.get("blender_runtime_execution_performed")
    )
    return {
        "schema_version": 1,
        "kind": "shared_toolbox_ai_to_ai_final_summary",
        "stamp": stamp,
        "passed": passed,
        "tools_available": [item["tool_name"] for item in tool_capabilities],
        "tool_capabilities": tool_capabilities,
        "tool_requests_executed_or_proposed": tool_requests,
        "reports_generated": facts.get("reports_generated", []),
        "remaining_gaps": remaining_gaps,
        "recommended_next_task_md": recommended_next_task_md,
        "compact_bundle_paths": bundle_paths,
        "provider_execution_performed": bool(facts.get("provider_execution_performed")),
        "provider_diagnostics": provider_diagnostics,
        "gpu_primary_advisory_succeeded": bool(provider_diagnostics.get("gpu_primary_advisory_succeeded")),
        "provider_failure_detected": bool(provider_diagnostics.get("provider_failure_detected")),
        "provider_advisory_state": provider_diagnostics.get("provider_advisory_state"),
        "provider_failure_reasons": provider_diagnostics.get("provider_failure_reasons", []),
        "degraded_provider_components": provider_diagnostics.get("degraded_provider_components", []),
        "deterministic_recovery_used": bool(provider_diagnostics.get("deterministic_recovery_used")),
        "patch_plan_summary": patch_plan_summary,
        "patch_plan_summary_seen": bool(patch_plan_summary.get("seen")),
        "patch_plan_count": patch_plan_summary.get("patch_plan_count", 0),
        "manual_review_required": patch_plan_summary.get("manual_review_required"),
        "patch_application_performed": bool(facts.get("patch_application_performed")),
        "source_writes_performed": bool(facts.get("source_writes_performed")),
        "sqlite_write_performed": bool(facts.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(facts.get("persistent_memory_write_performed")),
        "blender_runtime_execution_performed": bool(facts.get("blender_runtime_execution_performed")),
        "artifact_paths_considered": artifact_paths,
        "recursive_defaults": recursive_defaults or {},
        "chunked_file_index": chunked_file_index or [],
        "errors": facts.get("errors", []),
        "warnings": facts.get("warnings", []),
    }


def render_final_summary_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = ["# Shared Toolbox AI-to-AI Final Summary", ""]
    for key in (
        "stamp",
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "source_writes_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "blender_runtime_execution_performed",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Provider diagnostics")
    lines.append("")
    provider = summary.get("provider_diagnostics") or {}
    lines.append(f"- Provider execution seen: `{provider.get('provider_execution_seen')}`")
    lines.append(f"- GPU primary advisory succeeded: `{provider.get('gpu_primary_advisory_succeeded')}`")
    lines.append(f"- Provider failure detected: `{provider.get('provider_failure_detected')}`")
    lines.append(f"- Deterministic recovery used: `{provider.get('deterministic_recovery_used')}`")
    lines.append(f"- Provider advisory state: `{provider.get('provider_advisory_state')}`")
    reasons = provider.get("provider_failure_reasons") or []
    if reasons:
        lines.append("- Provider failure reasons:")
        for reason in reasons[:12]:
            lines.append(f"  - {reason}")
    for item in provider.get("diagnostics", [])[:12]:
        lines.append(
            f"- `{item.get('path')}` kind=`{item.get('kind')}` passed=`{item.get('passed')}` "
            f"provider_execution_performed=`{item.get('provider_execution_performed')}` errors=`{item.get('errors')}`"
        )
    lines.append("")
    lines.append("## Patch plan summary")
    lines.append("")
    patch_summary = summary.get("patch_plan_summary") or {}
    lines.append(f"- Seen: `{patch_summary.get('seen')}`")
    lines.append(f"- Source: `{patch_summary.get('source')}`")
    lines.append(f"- Patch plan count: `{patch_summary.get('patch_plan_count')}`")
    lines.append(f"- Manual review required: `{patch_summary.get('manual_review_required')}`")
    lines.append(f"- Patch application performed: `{patch_summary.get('patch_application_performed')}`")
    for item in patch_summary.get("top_items", [])[:20]:
        if isinstance(item, dict):
            lines.append(f"- `{item.get('id') or item.get('recommendation_id')}` status=`{item.get('status')}` targets=`{item.get('target_files')}`")
    lines.append("")
    lines.append("## Tools available")
    lines.append("")
    for tool in summary.get("tool_capabilities", []):
        lines.append(f"### {tool.get('tool_name')}")
        lines.append("")
        lines.append(f"- Category: {tool.get('category')}")
        lines.append(f"- Safe default mode: {tool.get('safe_default_mode')}")
        lines.append(f"- Recommended next use: {tool.get('recommended_next_use')}")
        lines.append(f"- Allowed args: `{tool.get('allowed_args')}`")
        lines.append("- Can do:")
        for item in tool.get("what_it_can_do", []):
            lines.append(f"  - {item}")
        lines.append("- Must not do:")
        for item in tool.get("what_it_must_not_do", []):
            lines.append(f"  - {item}")
        lines.append("")
    lines.append("## Tool requests executed or proposed")
    lines.append("")
    for request in summary.get("tool_requests_executed_or_proposed", []):
        lines.append(f"- {request.get('id')}: {request.get('tool')} - {request.get('reason')}")
    lines.append("")
    lines.append("## Reports generated")
    lines.append("")
    for report in summary.get("reports_generated", []):
        lines.append(
            f"- {report.get('path')} exists={report.get('exists')} json_ok={report.get('json_ok')} "
            f"kind={report.get('kind')} passed={report.get('passed')}"
        )
    lines.append("")
    lines.append("## Remaining gaps")
    lines.append("")
    gaps = summary.get("remaining_gaps") or []
    if gaps:
        for gap in gaps:
            if isinstance(gap, dict):
                label = gap.get("gap") or gap.get("path") or "gap"
                detail = gap.get("detail") or gap.get("reason") or ""
                lines.append(f"- {label}: {detail}")
            else:
                lines.append(f"- {gap}")
    else:
        lines.append("- No blocking report-only guardrail gaps detected.")
    lines.append("")
    lines.append("## Recommended next task")
    lines.append("")
    lines.append(str(summary.get("recommended_next_task_md") or ""))
    lines.append("")
    lines.append("## Recursive defaults")
    lines.append("")
    recursive_defaults = summary.get("recursive_defaults") or {}
    lines.append(f"- Enabled: `{recursive_defaults.get('enabled')}`")
    lines.append(f"- Discovered reports: `{len(recursive_defaults.get('discovered_reports') or [])}`")
    lines.append(f"- Discovered artifacts: `{len(recursive_defaults.get('discovered_artifacts') or [])}`")
    lines.append("")
    lines.append("## Chunked large JSON/Markdown files")
    lines.append("")
    chunked = summary.get("chunked_file_index") or []
    if chunked:
        for item in chunked:
            lines.append(
                f"- {item.get('path')} lines={item.get('line_count')} "
                f"chunks={item.get('chunk_count')} chunk_size={item.get('chunk_size_lines')}"
            )
            for chunk in item.get("chunks", []):
                lines.append(f"  - {chunk.get('chunk_id')} -> next: {chunk.get('next_chunk_id') or 'END'}")
    else:
        lines.append("- No JSON/Markdown file above the chunk threshold was detected.")
    lines.append("")
    lines.append("## Compact bundle paths")
    lines.append("")
    for path in summary.get("compact_bundle_paths", []):
        lines.append(f"- {path}")
    lines.append("")
    return "\n".join(lines)


def write_final_summary(repo_root: Path, summary: dict[str, Any]) -> tuple[Path, Path]:
    stamp = str(summary["stamp"])
    output_dir = repo_root / "output" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{DEFAULT_FINAL_SUMMARY_PREFIX}_{stamp}.json"
    md_path = output_dir / f"{DEFAULT_FINAL_SUMMARY_PREFIX}_{stamp}.md"
    write_json_report(summary, json_path)
    md_path.write_text(render_final_summary_markdown(summary), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--basename", default=None)
    parser.add_argument("--output-dir", default="docs/LOCAL_VALIDATION_EVIDENCE")
    parser.add_argument("--task-md", default="docs/LOCAL_AI_TASKS/shared-runtime-toolbox-ai-to-ai-next-task-2026-05-03.md")
    parser.add_argument("--architecture-md", default="docs/LOCAL_AI_TASKS/shared-runtime-toolbox-orchestration-architecture.md")
    parser.add_argument("--orchestrator-report", action="append", default=[])
    parser.add_argument("--gpu-report", action="append", default=[])
    parser.add_argument("--sync-report", action="append", default=[])
    parser.add_argument("--contract-replay-report", action="append", default=[])
    parser.add_argument("--code-interpreter-report", action="append", default=[])
    parser.add_argument("--python-syntax-report", action="append", default=[])
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--include-missing-optional", action="store_true")
    parser.add_argument("--validate-bundle", action="store_true")
    parser.add_argument("--validation-output", default=None)
    parser.add_argument("--max-included-artifact-chars", type=int, default=14000)
    parser.add_argument("--max-included-artifacts", type=int, default=40)
    parser.add_argument("--no-recursive-defaults", action="store_true", help="Disable bounded recursive default discovery for stamped JSON/Markdown files.")
    parser.add_argument("--recursive-report-root", action="append", default=[], help="Extra recursive root for stamped JSON reports; repeatable or comma-separated.")
    parser.add_argument("--recursive-artifact-root", action="append", default=[], help="Extra recursive root for stamped Markdown/JSON artifacts; repeatable or comma-separated.")
    parser.add_argument("--recursive-include-unstamped", action="store_true", help="Allow recursive discovery of files without the stamp in their path. Use only on narrow roots.")
    parser.add_argument("--recursive-max-files", type=int, default=DEFAULT_RECURSIVE_MAX_FILES)
    parser.add_argument("--chunk-large-files-lines", type=int, default=DEFAULT_CHUNK_LINES, help="Build pointer-style chunk metadata for JSON/Markdown files above this line count. Set 0 to disable.")
    return parser.parse_args(argv)


def build_shared_toolbox_bundle(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    stamp = args.stamp or datetime.now().strftime(DEFAULT_STAMP_FORMAT)
    basename = args.basename or f"{DEFAULT_BASENAME_PREFIX}_{stamp}"
    output_dir = resolve_output_path(repo_root, args.output_dir)

    explicit_reports = coalesce_list(
        list(args.report or []),
        list(args.orchestrator_report or []),
        list(args.gpu_report or []),
        list(args.sync_report or []),
        list(args.contract_replay_report or []),
        list(args.code_interpreter_report or []),
        list(args.python_syntax_report or []),
    )
    report_candidates = coalesce_list(explicit_reports, report_templates_for_stamp(stamp))
    reports, missing_reports = existing_paths(repo_root, report_candidates, label="report", include_missing_optional=bool(args.include_missing_optional))

    initial_bundle_paths = [
        repo_relative(output_dir / f"{basename}.json", repo_root),
        repo_relative(output_dir / f"{basename}.md", repo_root),
    ]
    artifact_candidates = coalesce_list([args.task_md, args.architecture_md], list(args.artifact or []), artifact_templates_for_stamp(stamp))
    artifacts, missing_artifacts = existing_paths(repo_root, artifact_candidates, label="artifact", include_missing_optional=bool(args.include_missing_optional))

    recursive_report_roots = [] if args.no_recursive_defaults else list(DEFAULT_RECURSIVE_REPORT_ROOTS)
    recursive_artifact_roots = [] if args.no_recursive_defaults else list(DEFAULT_RECURSIVE_ARTIFACT_ROOTS)
    recursive_report_roots = coalesce_list(recursive_report_roots, list(args.recursive_report_root or []))
    recursive_artifact_roots = coalesce_list(recursive_artifact_roots, list(args.recursive_artifact_root or []))

    summary = build_final_summary(
        repo_root=repo_root,
        stamp=stamp,
        report_paths=reports,
        artifact_paths=artifacts,
        bundle_paths=initial_bundle_paths,
        recommended_next_task_md=args.task_md,
        missing_reports=missing_reports,
        missing_artifacts=missing_artifacts,
    )
    final_json, final_md = write_final_summary(repo_root, summary)
    reports_with_summary = coalesce_list(reports, [repo_relative(final_json, repo_root)])
    artifacts_with_summary = coalesce_list(artifacts, [repo_relative(final_md, repo_root)])

    bundle, outputs_text = build_bundle(
        repo_root,
        reports_with_summary,
        basename,
        output_dir,
        [],
        artifacts_with_summary,
        True,
        int(args.max_included_artifact_chars),
        int(args.max_included_artifacts),
        recursive_report_roots,
        recursive_artifact_roots,
        stamp,
        bool(args.recursive_include_unstamped),
        int(args.recursive_max_files),
        int(args.chunk_large_files_lines),
    )
    bundle_paths = outputs_text.splitlines()
    summary["compact_bundle_paths"] = [repo_relative(Path(path), repo_root) for path in bundle_paths]
    summary["recursive_defaults"] = bundle.get("recursive_default_discovery", {})
    summary["chunked_file_index"] = bundle.get("artifact_chunk_index", [])
    final_json, final_md = write_final_summary(repo_root, summary)

    # Rebuild once so the included final summary artifact contains the final
    # bundle path, recursive discovery and chunk index metadata.
    bundle, outputs_text = build_bundle(
        repo_root,
        reports_with_summary,
        basename,
        output_dir,
        [],
        artifacts_with_summary,
        True,
        int(args.max_included_artifact_chars),
        int(args.max_included_artifacts),
        recursive_report_roots,
        recursive_artifact_roots,
        stamp,
        bool(args.recursive_include_unstamped),
        int(args.recursive_max_files),
        int(args.chunk_large_files_lines),
    )
    bundle_paths = outputs_text.splitlines()

    validation_report: dict[str, Any] | None = None
    validation_output_path: Path | None = None
    if args.validate_bundle:
        bundle_json = output_dir / f"{basename}.json"
        validation_report = validate_github_evidence_bundles(repo_root, [bundle_json])
        validation_output = args.validation_output or f"output/validation/{basename}_validation.json"
        validation_output_path = resolve_output_path(repo_root, validation_output)
        write_json_report(validation_report, validation_output_path)

    return {
        "schema_version": 1,
        "kind": "shared_toolbox_ai_to_ai_bundle_builder_result",
        "repo_root": str(repo_root),
        "stamp": stamp,
        "passed": bool(summary.get("passed")) and (validation_report is None or bool(validation_report.get("passed"))),
        "final_summary_json": repo_relative(final_json, repo_root),
        "final_summary_markdown": repo_relative(final_md, repo_root),
        "bundle_outputs": [repo_relative(Path(path), repo_root) for path in bundle_paths],
        "validation_output": repo_relative(validation_output_path, repo_root) if validation_output_path else None,
        "bundle_decision": bundle.get("decision"),
        "provider_execution_performed": bool(summary.get("provider_execution_performed")),
        "patch_application_performed": bool(summary.get("patch_application_performed")),
        "sqlite_write_performed": bool(summary.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(summary.get("persistent_memory_write_performed")),
        "recursive_default_discovery": bundle.get("recursive_default_discovery", {}),
        "artifact_chunk_index": bundle.get("artifact_chunk_index", []),
        "errors": list(summary.get("errors") or []) + list((validation_report or {}).get("errors") or []),
        "warnings": list(summary.get("warnings") or []) + list((validation_report or {}).get("warnings") or []),
        "missing_reports": missing_reports,
        "missing_artifacts": missing_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_shared_toolbox_bundle(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
