#!/usr/bin/env python3
"""Replacement-ready orchestrator for build_github_evidence_bundle.py.

This file is intentionally kept separate so it can be manually copied over
`Tools/ai/build_github_evidence_bundle.py` after syncing PR #109 locally.

It preserves the public CLI and delegates implementation details to the split
`github_evidence_bundle_*` modules.

It does not execute providers, run Blender, apply patches or modify runtime
outputs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from Tools.ai.github_evidence_bundle_artifacts import build_included_artifacts, summarize_artifact
from Tools.ai.github_evidence_bundle_decisions import build_decision
from Tools.ai.github_evidence_bundle_io import (
    CONTENT_EXTENSION_ALLOWLIST,
    DEFAULT_INCLUDED_ARTIFACT_CHARS,
    DEFAULT_MAX_INCLUDED_ARTIFACTS,
    DEFAULT_REPORTS,
    RAW_ARTIFACT_DENY_FRAGMENTS,
    RAW_ARTIFACT_DENY_PREFIXES,
    resolve_repo_path,
    split_path_values,
)
from Tools.ai.github_evidence_bundle_markdown import render_markdown
from Tools.ai.github_evidence_bundle_reports import (
    discover_selected_chunks_evidence,
    summarize_report,
    summarize_selected_chunks_evidence,
)


def build_bundle(
    repo_root: Path,
    report_paths: list[str],
    basename: str,
    output_dir: Path,
    selected_chunks_paths: list[str],
    artifact_paths: list[str],
    auto_include_related: bool,
    max_included_artifact_chars: int,
    max_included_artifacts: int,
) -> tuple[dict[str, Any], str]:
    """Build and write the JSON/Markdown evidence bundle."""
    resolved_reports = [resolve_repo_path(repo_root, raw) for raw in report_paths]
    reports = [summarize_report(path, repo_root) for path in resolved_reports]
    artifact_manifest = [summarize_artifact(path, repo_root) for path in resolved_reports]
    selected_paths = discover_selected_chunks_evidence(repo_root, selected_chunks_paths)
    selected_chunks_evidence = [summarize_selected_chunks_evidence(path, repo_root) for path in selected_paths]
    explicit_artifacts = [resolve_repo_path(repo_root, raw) for raw in split_path_values(artifact_paths)]
    included_artifacts = build_included_artifacts(
        repo_root,
        resolved_reports,
        explicit_artifacts,
        auto_include_related=auto_include_related,
        max_chars=max_included_artifact_chars,
        max_artifacts=max_included_artifacts,
    )

    bundle = {
        "schema_version": 1,
        "kind": "github_validation_evidence_bundle",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "source_reports": [item["path"] for item in reports],
        "source_selected_chunks_evidence": [item["path"] for item in selected_chunks_evidence],
        "source_included_artifacts": [item["path"] for item in included_artifacts],
        "reports": reports,
        "selected_chunks_evidence": selected_chunks_evidence,
        "artifact_manifest": artifact_manifest,
        "included_artifacts": included_artifacts,
        "included_artifact_policy": {
            "auto_include_related_artifacts": auto_include_related,
            "max_included_artifact_chars": max_included_artifact_chars,
            "max_included_artifacts": max_included_artifacts,
            "content_extension_allowlist": sorted(CONTENT_EXTENSION_ALLOWLIST),
            "raw_artifact_deny_prefixes": list(RAW_ARTIFACT_DENY_PREFIXES),
            "raw_artifact_deny_fragments": list(RAW_ARTIFACT_DENY_FRAGMENTS),
        },
        "decision": build_decision(reports, selected_chunks_evidence, artifact_manifest, included_artifacts),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    json_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(bundle), encoding="utf-8")
    return bundle, f"{json_path}\n{md_path}"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--basename", default="latest_ai_workflow_evidence")
    parser.add_argument("--output-dir", default="docs/LOCAL_VALIDATION_EVIDENCE")
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[], help="Extra artifact file to include with bounded content; repeatable or comma-separated.")
    parser.add_argument("--no-auto-include-related-artifacts", action="store_true", help="Disable automatic inclusion of sibling/declared related artifacts.")
    parser.add_argument("--max-included-artifact-chars", type=int, default=DEFAULT_INCLUDED_ARTIFACT_CHARS)
    parser.add_argument("--max-included-artifacts", type=int, default=DEFAULT_MAX_INCLUDED_ARTIFACTS)
    parser.add_argument(
        "--selected-chunks-evidence",
        action="append",
        default=[],
        help="Compact selected-chunks evidence JSON path. Repeatable or comma-separated. If omitted, docs/LOCAL_VALIDATION_EVIDENCE/*selected_chunks_evidence.json is discovered when present.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    report_paths = split_path_values(args.report) or list(DEFAULT_REPORTS)
    bundle, outputs = build_bundle(
        repo_root,
        report_paths,
        args.basename,
        output_dir,
        list(args.selected_chunks_evidence or []),
        list(args.artifact or []),
        not args.no_auto_include_related_artifacts,
        args.max_included_artifact_chars,
        args.max_included_artifacts,
    )
    print(json.dumps({"passed": True, "outputs": outputs.splitlines(), "decision": bundle["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
