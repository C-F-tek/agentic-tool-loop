#!/usr/bin/env python3
"""Build compact Git-trackable GitHub evidence bundles.

The builder is report-only. It reads validation/report artifacts, optionally
includes bounded related artifacts, writes compact JSON/Markdown evidence under
`docs/LOCAL_VALIDATION_EVIDENCE`, and never executes providers, Blender, Git
writes, patch application, or SQLite writes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from Tools.ai.github_evidence_bundle_artifacts import (
    DEFAULT_CHUNK_LINES,
    DEFAULT_RECURSIVE_MAX_FILES,
    build_artifact_chunk_index,
    build_included_artifacts,
    discover_recursive_artifacts,
    summarize_artifact,
)
from Tools.ai.github_evidence_bundle_decisions import build_decision
from Tools.ai.github_evidence_bundle_io import (
    CONTENT_EXTENSION_ALLOWLIST,
    DEFAULT_INCLUDED_ARTIFACT_CHARS,
    DEFAULT_MAX_INCLUDED_ARTIFACTS,
    DEFAULT_REPORTS,
    RAW_ARTIFACT_DENY_FRAGMENTS,
    RAW_ARTIFACT_DENY_PREFIXES,
    normalize_manifest_path,
    resolve_repo_path,
    split_path_values,
)
from Tools.ai.github_evidence_bundle_markdown import render_markdown
from Tools.ai.github_evidence_bundle_reports import (
    discover_selected_chunks_evidence,
    summarize_report,
    summarize_selected_chunks_evidence,
)


def dedupe_paths(paths: list[Path]) -> list[Path]:
    """Return paths deduplicated by resolved path while preserving order."""
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = path.resolve().as_posix() if path.exists() else path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


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
    recursive_report_roots: list[str] | None = None,
    recursive_artifact_roots: list[str] | None = None,
    recursive_stamp: str | None = None,
    recursive_include_unstamped: bool = False,
    recursive_max_files: int = DEFAULT_RECURSIVE_MAX_FILES,
    chunk_large_files_lines: int = 0,
    auto_discover_selected_chunks_evidence: bool = True,
) -> tuple[dict[str, Any], str]:
    """Build and write the JSON/Markdown evidence bundle.

    The trailing recursive/chunk parameters are optional to preserve the original
    public Python API. Older callers that pass the first nine positional
    arguments continue to work unchanged.
    """
    resolved_reports = [resolve_repo_path(repo_root, raw) for raw in report_paths]
    explicit_artifacts = [resolve_repo_path(repo_root, raw) for raw in split_path_values(artifact_paths)]

    recursive_report_paths, skipped_recursive_reports = discover_recursive_artifacts(
        repo_root,
        split_path_values(list(recursive_report_roots or [])),
        suffixes=(".json",),
        stamp=recursive_stamp,
        include_unstamped=recursive_include_unstamped,
        max_files=recursive_max_files,
    )
    recursive_artifact_paths, skipped_recursive_artifacts = discover_recursive_artifacts(
        repo_root,
        split_path_values(list(recursive_artifact_roots or [])),
        suffixes=(".json", ".md"),
        stamp=recursive_stamp,
        include_unstamped=recursive_include_unstamped,
        max_files=recursive_max_files,
    )

    resolved_reports = dedupe_paths(resolved_reports + recursive_report_paths)
    explicit_artifacts = dedupe_paths(explicit_artifacts)
    recursive_artifact_paths = dedupe_paths(recursive_artifact_paths)

    reports = [summarize_report(path, repo_root) for path in resolved_reports]
    artifact_manifest = [summarize_artifact(path, repo_root) for path in resolved_reports]
    selected_paths = discover_selected_chunks_evidence(
        repo_root,
        selected_chunks_paths,
        auto_discover=auto_discover_selected_chunks_evidence,
    )
    selected_chunks_evidence = [summarize_selected_chunks_evidence(path, repo_root) for path in selected_paths]
    included_artifacts = build_included_artifacts(
        repo_root,
        resolved_reports,
        explicit_artifacts,
        auto_include_related=auto_include_related,
        max_chars=max_included_artifact_chars,
        max_artifacts=max_included_artifacts,
        recursive_artifact_paths=recursive_artifact_paths,
        max_lines_per_chunk=chunk_large_files_lines,
    )
    chunk_index_source_paths = dedupe_paths(resolved_reports + explicit_artifacts + recursive_artifact_paths)
    artifact_chunk_index = build_artifact_chunk_index(
        repo_root,
        chunk_index_source_paths,
        max_lines_per_chunk=chunk_large_files_lines,
    )

    recursive_default_discovery = {
        "enabled": bool(recursive_report_roots or recursive_artifact_roots),
        "stamp": recursive_stamp,
        "include_unstamped": recursive_include_unstamped,
        "max_files": recursive_max_files,
        "report_roots": split_path_values(list(recursive_report_roots or [])),
        "artifact_roots": split_path_values(list(recursive_artifact_roots or [])),
        "discovered_reports": [normalize_manifest_path(path, repo_root) for path in recursive_report_paths],
        "discovered_artifacts": [normalize_manifest_path(path, repo_root) for path in recursive_artifact_paths],
        "skipped_reports": skipped_recursive_reports[:200],
        "skipped_artifacts": skipped_recursive_artifacts[:200],
    }

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
        "artifact_chunk_index": artifact_chunk_index,
        "recursive_default_discovery": recursive_default_discovery,
        "included_artifact_policy": {
            "auto_include_related_artifacts": auto_include_related,
            "max_included_artifact_chars": max_included_artifact_chars,
            "max_included_artifacts": max_included_artifacts,
            "chunk_large_files_lines": chunk_large_files_lines,
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
    parser.add_argument("--recursive-report-root", action="append", default=[], help="Bounded recursive root for stamped JSON reports. Repeatable or comma-separated.")
    parser.add_argument("--recursive-artifact-root", action="append", default=[], help="Bounded recursive root for stamped JSON/Markdown artifacts. Repeatable or comma-separated.")
    parser.add_argument("--recursive-stamp", default=None, help="Only include recursive files whose path contains this stamp unless --recursive-include-unstamped is set.")
    parser.add_argument("--recursive-include-unstamped", action="store_true", help="Allow recursive discovery of files without the recursive stamp. Use only on narrow roots.")
    parser.add_argument("--recursive-max-files", type=int, default=DEFAULT_RECURSIVE_MAX_FILES)
    parser.add_argument("--chunk-large-files-lines", type=int, default=DEFAULT_CHUNK_LINES, help="Add pointer-linked chunk metadata for JSON/Markdown artifacts above this line count. Set 0 to disable.")
    parser.add_argument(
        "--selected-chunks-evidence",
        action="append",
        default=[],
        help="Compact selected-chunks evidence JSON path. Repeatable or comma-separated. If omitted, docs/LOCAL_VALIDATION_EVIDENCE/*selected_chunks_evidence.json is discovered when present.",
    )
    parser.add_argument(
        "--no-auto-discover-selected-chunks-evidence",
        action="store_true",
        help="Do not discover old docs/LOCAL_VALIDATION_EVIDENCE/*selected_chunks_evidence.json when no explicit selected-chunks evidence path is supplied.",
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
        list(args.recursive_report_root or []),
        list(args.recursive_artifact_root or []),
        args.recursive_stamp,
        bool(args.recursive_include_unstamped),
        int(args.recursive_max_files),
        int(args.chunk_large_files_lines),
        not bool(args.no_auto_discover_selected_chunks_evidence),
    )
    print(json.dumps({"passed": True, "outputs": outputs.splitlines(), "decision": bundle["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
