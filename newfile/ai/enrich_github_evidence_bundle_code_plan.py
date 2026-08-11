#!/usr/bin/env python3
"""Enrich GitHub evidence bundles with code patch-plan summaries.

This post-processor keeps the existing evidence bundle builder stable while
adding native summary support for `agent_review_code_patch_plan` artifacts.
It reads an existing compact bundle, inspects its report/artifact references,
and rewrites bounded JSON/Markdown evidence with code patch-plan metadata.

It does not execute providers, run Blender, apply patches or write source files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.build_github_evidence_bundle import (  # noqa: E402
    compact_patch_plan,
    read_json,
    render_markdown,
)
from Tools.ai.code_patch_plan_common import (  # noqa: E402
    now_iso,
    report_only_guardrails,
    resolve_output_path,
)

REPORT_KIND = "github_validation_evidence_bundle_code_plan_enrichment"
SUPPORTED_PLAN_KIND = "agent_review_code_patch_plan"


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    """Resolve a path against the repository root."""
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def summarize_code_patch_plan(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return a compact summary for agent_review_code_patch_plan reports."""
    if data.get("kind") != SUPPORTED_PLAN_KIND:
        return None
    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    plans = data.get("code_patch_plans") if isinstance(data.get("code_patch_plans"), list) else []
    static_count = data.get("static_code_patch_plan_count")
    contract_count = data.get("code_contract_patch_plan_count")
    return {
        "patch_plan_count": data.get("patch_plan_count", len(plans)),
        "code_contract_patch_plan_count": contract_count,
        "static_code_patch_plan_count": static_count,
        "manual_review_required": data.get("manual_review_required") or decision.get("manual_review_required"),
        "ready_for_manual_review": decision.get("ready_for_manual_review"),
        "recommended_next_layer": decision.get("recommended_next_layer"),
        "provider_execution_performed": data.get("provider_execution_performed"),
        "patch_application_performed": data.get("patch_application_performed"),
        "source_writes_performed": data.get("source_writes_performed"),
        "plans": [compact_patch_plan(plan) for plan in plans if isinstance(plan, dict)],
    }


def report_paths(bundle: dict[str, Any]) -> list[str]:
    """Return report paths from a bundle."""
    paths: list[str] = []
    for item in bundle.get("reports", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def included_artifact_paths(bundle: dict[str, Any]) -> list[str]:
    """Return included artifact paths from a bundle."""
    paths: list[str] = []
    for item in bundle.get("included_artifacts", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def patch_plan_summary_fields(summary: dict[str, Any]) -> dict[str, Any]:
    """Return top-level report summary fields derived from patch-plan summary."""
    return {
        "patch_plan_summary": summary,
        "patch_plan_count": summary.get("patch_plan_count"),
        "static_code_patch_plan_count": summary.get("static_code_patch_plan_count"),
        "code_contract_patch_plan_count": summary.get("code_contract_patch_plan_count"),
        "recommended_next_layer": summary.get("recommended_next_layer"),
    }


def report_entry_for_code_patch_plan(raw: str, data: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """Build a bundle report entry for a discovered code patch-plan report."""
    return {
        "path": raw,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "passed": data.get("passed"),
        "summary": {
            "schema_version": data.get("schema_version"),
            "kind": data.get("kind"),
            "passed": data.get("passed"),
            "provider_execution_performed": data.get("provider_execution_performed"),
            "patch_application_performed": data.get("patch_application_performed"),
            "source_writes_performed": data.get("source_writes_performed"),
            "errors": data.get("errors") or [],
            "warnings": data.get("warnings") or [],
            **patch_plan_summary_fields(summary),
        },
    }


def attach_summary_to_report(bundle: dict[str, Any], path_value: str, summary: dict[str, Any]) -> bool:
    """Attach a code patch-plan summary to an existing report entry if present."""
    for item in bundle.get("reports", []):
        if not isinstance(item, dict) or item.get("path") != path_value:
            continue
        current = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        current.update(patch_plan_summary_fields(summary))
        item["summary"] = current
        return True
    return False


def discover_and_apply(repo_root: Path, bundle: dict[str, Any]) -> tuple[int, list[str]]:
    """Discover code patch-plan reports referenced by the bundle and enrich it."""
    enriched = 0
    warnings: list[str] = []
    candidates = report_paths(bundle) + included_artifact_paths(bundle)
    seen: set[str] = set()
    for raw in candidates:
        if raw in seen:
            continue
        seen.add(raw)
        path = resolve_repo_path(repo_root, raw)
        if path.suffix.lower() != ".json" or not path.exists():
            continue
        data = read_json(path)
        if not data:
            continue
        summary = summarize_code_patch_plan(data)
        if not summary:
            continue
        attached = attach_summary_to_report(bundle, raw, summary)
        if not attached:
            bundle.setdefault("reports", []).append(report_entry_for_code_patch_plan(raw, data, summary))
        enriched += 1
    if enriched == 0:
        warnings.append("no agent_review_code_patch_plan report found for enrichment")
    return enriched, warnings


def enrich_bundle(repo_root: Path, bundle_path: Path, output_path: Path | None, markdown_output: Path | None) -> dict[str, Any]:
    """Enrich one existing evidence bundle and write JSON/Markdown outputs."""
    bundle = read_json(bundle_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not bundle:
        errors.append(f"could not read bundle: {bundle_path}")
        bundle = {
            "schema_version": 1,
            "kind": "github_validation_evidence_bundle",
            "generated_at": now_iso(),
            "repo_root": str(repo_root),
            "reports": [],
            "decision": {},
        }
    enriched_count, enrich_warnings = discover_and_apply(repo_root, bundle)
    warnings.extend(enrich_warnings)
    decision = bundle.get("decision") if isinstance(bundle.get("decision"), dict) else {}
    decision["patch_plan_summary_seen"] = any(
        bool((item.get("summary") or {}).get("patch_plan_summary"))
        for item in bundle.get("reports", [])
        if isinstance(item, dict)
    )
    decision["code_patch_plan_summary_enriched_count"] = enriched_count
    bundle["decision"] = decision
    bundle["code_patch_plan_enrichment"] = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "enriched_count": enriched_count,
        "guardrails": report_only_guardrails(
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }
    target_json = output_path or bundle_path
    target_md = markdown_output or bundle_path.with_suffix(".md")
    target_json.parent.mkdir(parents=True, exist_ok=True)
    target_md.parent.mkdir(parents=True, exist_ok=True)
    target_json.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    target_md.write_text(render_markdown(bundle), encoding="utf-8")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--output", help="Optional enriched JSON output path. Defaults to overwrite bundle.")
    parser.add_argument("--markdown-output", help="Optional enriched Markdown output path. Defaults to bundle .md.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    bundle = enrich_bundle(
        repo_root,
        resolve_output_path(repo_root, args.bundle),
        resolve_output_path(repo_root, args.output) if args.output else None,
        resolve_output_path(repo_root, args.markdown_output) if args.markdown_output else None,
    )
    enrichment = bundle.get("code_patch_plan_enrichment") if isinstance(bundle.get("code_patch_plan_enrichment"), dict) else {}
    print(json.dumps({"passed": enrichment.get("passed", False), "enriched_count": enrichment.get("enriched_count", 0), "decision": bundle.get("decision", {})}, indent=2))
    return 0 if enrichment.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
