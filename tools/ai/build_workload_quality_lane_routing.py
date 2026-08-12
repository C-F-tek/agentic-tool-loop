#!/usr/bin/env python3
"""Build a report-only AI workload quality lane-routing report.

This tool is the explicit implementation surface for
P-AI-WORKLOAD-QUALITY-BASED-LANE-ROUTING. It consumes the workload quality gate
report and optional candidate context files, then emits a deterministic routing
report that downstream packet/proposal builders can use to trust only usable
workload lanes.

It never executes providers and never modifies Blender/runtime/legacy outputs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def _ensure_repo_imports(repo_root: Path) -> None:
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def split_path_values(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out


def _default_context_files(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    checks = report.get("checks") or {}
    results = checks.get("results") if isinstance(checks, dict) else []
    if not isinstance(results, list):
        return []
    return [str(item.get("path")) for item in results if isinstance(item, dict) and item.get("path")]


def _primary_advisory_provider(advisory_lanes: list[str]) -> dict[str, Any]:
    """Map usable workload lanes to the primary advisory provider contract."""

    if "ollama" in advisory_lanes:
        return {
            "provider": "ollama",
            "compute_lane": "gpu_cuda",
            "role": "primary_advisory",
            "execution_mode": "explicit_only",
            "enabled_by_flag": "--use-primary-advisory-provider / -UsePrimaryAdvisoryProvider",
            "provider_execution_performed": False,
        }
    return {
        "provider": None,
        "compute_lane": None,
        "role": "none",
        "execution_mode": "unavailable_no_usable_lane",
        "enabled_by_flag": None,
        "provider_execution_performed": False,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    routing = report["routing"]
    provider = report.get("primary_advisory_provider", {})
    lines = ["# AI Workload Quality Lane Routing", ""]
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Quality report present: `{routing['quality_report_present']}`")
    lines.append(f"- Advisory lanes: `{', '.join(routing['advisory_lanes']) or 'none'}`")
    lines.append(f"- Excluded advisory lanes: `{', '.join(routing['excluded_advisory_lanes']) or 'none'}`")
    lines.append(f"- Primary advisory provider: `{provider.get('provider') or 'none'}`")
    lines.append(f"- Primary compute lane: `{provider.get('compute_lane') or 'none'}`")
    lines.append("")
    lines.append("## Trusted context files")
    lines.append("")
    trusted = routing.get("trusted_context_files") or []
    if trusted:
        for item in trusted:
            lane = item.get("lane") or "untracked"
            lines.append(f"- `{item['path']}` — lane `{lane}`, reason `{item['reason']}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Excluded context files")
    lines.append("")
    excluded = routing.get("excluded_context_files") or []
    if excluded:
        for item in excluded:
            lane = item.get("lane") or "unknown"
            lines.append(f"- `{item['path']}` — lane `{lane}`, reason `{item['reason']}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for condition in report["stop_conditions"]:
        lines.append(f"- {condition}")
    return "\n".join(lines) + "\n"


def build_lane_routing_report(repo_root: Path, quality_report_path: Path, context_files: list[str]) -> dict[str, Any]:
    from Tools.ai.workload_quality import (  # noqa: PLC0415
        build_quality_routing_summary,
        load_workload_quality_report,
        route_context_files_by_quality,
    )

    quality_report = load_workload_quality_report(repo_root, quality_report_path)
    candidates = context_files or _default_context_files(quality_report)
    routing = route_context_files_by_quality(candidates, quality_report)
    summary = build_quality_routing_summary(quality_report)
    primary_provider = _primary_advisory_provider(list(summary.get("advisory_lanes") or []))
    routing["primary_advisory_provider"] = primary_provider
    summary["primary_advisory_provider"] = primary_provider

    errors: list[str] = []
    warnings: list[str] = []
    if not summary["quality_report_present"]:
        warnings.append("quality report is missing; no workload-specific context was excluded")
    if not summary["advisory_lanes"]:
        warnings.append("no usable workload lanes are available for advisory context")

    return {
        "schema_version": 1,
        "kind": "ai_workload_quality_lane_routing",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "mode": "report_only_quality_based_lane_routing",
        "policy": "usable_text_lanes_only_for_advisory_context",
        "quality_report": str(quality_report_path),
        "primary_advisory_provider": primary_provider,
        "routing": routing,
        "summary": summary,
        "stop_conditions": [
            "Any change would execute providers implicitly or by default.",
            "Any change would use an unusable workload report as advisory context.",
            "Any change would alter NPU/Ollama model configuration, prompt prose or provider orchestration.",
            "Any change would touch Blender runtime, Ready To Jazz, full analysis JSON, output legacy or generated indexes by hand.",
            "Any change would introduce OpenVINO GPU as a primary lane.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--quality-report", default="output/validation/ai_workload_report_quality.json")
    parser.add_argument("--context-file", action="append", default=[], help="Candidate context file. Repeatable or comma-separated.")
    parser.add_argument("--output", default="output/validation/ai_workload_quality_lane_routing.json")
    parser.add_argument("--markdown-output", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    _ensure_repo_imports(repo_root)
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # noqa: PLC0415

    quality_report_path = Path(args.quality_report)
    if not quality_report_path.is_absolute():
        quality_report_path = repo_root / quality_report_path

    report = build_lane_routing_report(
        repo_root,
        quality_report_path,
        split_path_values(list(args.context_file or [])),
    )
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    if args.markdown_output:
        markdown_output = resolve_output_path(repo_root, args.markdown_output)
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_render_markdown(report), encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
