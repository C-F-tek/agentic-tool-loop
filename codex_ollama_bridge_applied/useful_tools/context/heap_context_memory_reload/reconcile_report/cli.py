#!/usr/bin/env python3
"""Reconcile heap completeness report with startup context/memory reload artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

STARTUP_REQUIREMENT_TO_ARTIFACT_KEYS: dict[str, tuple[str, ...]] = {
    "tool_catalog": ("tool_catalog_json", "tool_catalog_markdown"),
    "shared_memory": ("shared_memory_json", "shared_memory_markdown"),
    "operational_memory_write": (
        "operational_memory_write_json",
        "operational_memory_write_markdown",
        "operational_memory_status_json",
        "operational_memory_status_markdown",
    ),
    "operational_memory_search": (
        "operational_memory_search_json",
        "operational_memory_search_markdown",
    ),
    "shared_context_chunks": ("shared_context_json", "shared_context_markdown"),
    "semantic_code_chunks": (
        "semantic_code_chunks_json",
        "semantic_code_chunks_markdown",
    ),
    "ai_context_pack": (
        "ai_context_pack_json",
        "ai_context_pack_markdown",
        "ai_context_pack_evidence_json",
    ),
    "semantic_evidence_chunks": (
        "semantic_evidence_chunks_json",
        "semantic_evidence_chunks_markdown",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def relpath(path_value: str, repo_root: Path) -> str:
    p = Path(path_value)
    try:
        return p.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except Exception:
        return str(path_value).replace("\\", "/")


def append_ref(refs: list[str], value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    normalized = value.replace("\\", "/")
    if normalized not in refs:
        refs.append(normalized)


def useful_artifact_refs(manifest: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        for value in artifacts.values():
            append_ref(refs, value)

    for execution in manifest.get("tool_executions") or []:
        if not isinstance(execution, dict):
            continue
        for key in (
            "useful_artifact_paths",
            "existing_artifact_paths",
            "artifact_paths",
        ):
            for value in execution.get(key) or []:
                append_ref(refs, value)
        for summary in execution.get("artifact_summaries") or []:
            if isinstance(summary, dict):
                append_ref(refs, summary.get("path"))
        for artifact in execution.get("artifacts") or []:
            if isinstance(artifact, dict):
                append_ref(refs, artifact.get("path"))
            else:
                append_ref(refs, artifact)
    return refs


def completed_from_startup(
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, list[str]]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    completed: list[str] = []
    requirement_refs: dict[str, list[str]] = {}
    for requirement, keys in STARTUP_REQUIREMENT_TO_ARTIFACT_KEYS.items():
        refs = [
            str(artifacts.get(key) or "").replace("\\", "/")
            for key in keys
            if str(artifacts.get(key) or "").strip()
        ]
        if refs:
            completed.append(requirement)
            requirement_refs[requirement] = refs
    return completed, requirement_refs


def startup_input_ready(startup: dict[str, Any]) -> bool:
    contract = startup.get("contract") if isinstance(startup.get("contract"), dict) else {}
    return bool(
        startup.get("passed") is True
        or startup.get("input_ready_before_heap") is True
        or contract.get("input_ready_before_heap") is True
    )


def render_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Heap Startup Context Reconciliation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Startup manifest: `{report.get('startup_manifest')}`",
        f"- Heap report: `{report.get('heap_report')}`",
        f"- Startup degraded: `{report.get('startup_degraded')}`",
        f"- Degraded startup reconciled: `{report.get('degraded_startup_reconciled')}`",
        f"- Requirements completed from startup: `{len(report.get('requirements_completed_from_startup') or [])}`",
        "",
        "## Completed from startup",
        "",
    ]
    for item in report.get("requirements_completed_from_startup") or []:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Remaining missing requirements", ""])
    for item in report.get("remaining_missing_requirements") or []:
        lines.append(f"- `{item}`")
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--startup-manifest", required=True)
    parser.add_argument("--heap-report", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument(
        "--allow-degraded-startup",
        action="store_true",
        help="Deprecated compatibility flag; degraded startup is not reconciled as usable.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    startup_manifest_path = Path(args.startup_manifest).resolve()
    heap_report_path = Path(args.heap_report).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else heap_report_path.with_name("heap_startup_context_reconciliation.json")
    )
    markdown_output = (
        Path(args.markdown_output).resolve() if args.markdown_output else output.with_suffix(".md")
    )

    startup = load_json(startup_manifest_path)
    heap = load_json(heap_report_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not startup:
        errors.append(f"startup manifest unreadable: {startup_manifest_path}")
    if not heap:
        errors.append(f"heap report unreadable: {heap_report_path}")

    startup_passed = startup_input_ready(startup)
    startup_degraded = bool(
        startup.get("startup_reload_degraded") is True or startup.get("degraded_requirements")
    )
    if not startup_passed:
        errors.append("startup manifest did not pass and is not input_ready_before_heap")
    if startup_degraded:
        errors.append(
            "startup manifest is degraded; internal runtime surfaces must be repaired before reconciliation"
        )

    completed_from_preload, requirement_refs = completed_from_startup(startup)
    artifact_refs = useful_artifact_refs(startup)
    if args.allow_degraded_startup and startup_degraded:
        warnings.append("--allow-degraded-startup ignored; degraded startup remains blocking")

    if not errors:
        completed = list(heap.get("completed_requirements") or [])
        missing = list(heap.get("missing_requirements") or [])
        for requirement in completed_from_preload:
            if requirement not in completed:
                completed.append(requirement)
            if requirement in missing:
                missing.remove(requirement)

        heap["startup_preload_reconciled_into_report"] = True
        heap["startup_preload_integrated"] = True
        heap["startup_preload_ingested_into_heap"] = heap.get(
            "startup_preload_ingested_into_heap", "unknown"
        )
        heap["startup_preload_seen_by_provider_lanes"] = heap.get(
            "startup_preload_seen_by_provider_lanes", "unknown"
        )
        heap["startup_manifest"] = relpath(str(startup_manifest_path), repo_root)
        heap["startup_preload_integrated_at"] = datetime.now().isoformat(timespec="seconds")
        heap["startup_preload_requirement_refs"] = requirement_refs
        heap["startup_reload_degraded"] = startup_degraded
        heap["completed_requirements"] = completed
        heap["missing_requirements"] = missing
        heap["context_artifact_refs"] = sorted(
            set(list(heap.get("context_artifact_refs") or []) + artifact_refs)
        )
        heap.setdefault("warnings", [])
        if isinstance(heap["warnings"], list):
            heap["warnings"].append("startup preload artifacts reconciled into heap report state")
            if startup_degraded:
                heap["warnings"].append(
                    "startup preload was degraded; reconciliation did not prove provider consumption"
                )
        if missing:
            product_status_suggestion = "blocked_with_reason"
        elif not heap.get("proposal_iteration_artifacts") and not heap.get("provider_results"):
            product_status_suggestion = "blocked_waiting_for_provider_or_proposal"
        else:
            product_status_suggestion = heap.get("product_status") or "ready"
        heap["startup_reconciliation_product_status_suggestion"] = product_status_suggestion
        heap["startup_reconciliation_does_not_mutate_product_status"] = True
        write_json(heap_report_path, heap)

    report = {
        "schema_version": 1,
        "kind": "heap_startup_context_reconciliation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": repo_root.as_posix(),
        "startup_manifest": relpath(str(startup_manifest_path), repo_root),
        "heap_report": relpath(str(heap_report_path), repo_root),
        "passed": not errors,
        "startup_passed": startup_passed,
        "startup_degraded": startup_degraded,
        "allow_degraded_startup": bool(args.allow_degraded_startup),
        "degraded_startup_reconciled": bool(
            startup_degraded and args.allow_degraded_startup and not errors
        ),
        "requirements_completed_from_startup": completed_from_preload,
        "remaining_missing_requirements": (
            heap.get("missing_requirements") if isinstance(heap, dict) else []
        ),
        "product_status_preserved": heap.get("product_status") if isinstance(heap, dict) else "",
        "product_status_suggestion": (
            heap.get("startup_reconciliation_product_status_suggestion")
            if isinstance(heap, dict)
            else ""
        ),
        "artifact_ref_count": len(artifact_refs),
        "artifact_refs": artifact_refs,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "errors": errors,
        "warnings": warnings,
    }
    write_json(output, report)
    render_markdown(report, markdown_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
