"""CLI entrypoint for semantic evidence chunk generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive import write_zip
from .chunker import chunk_one_source
from .common import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_LINES,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OUTPUT_DIR,
    now_iso,
    repo_rel,
    resolve_output_path,
    split_path_values,
    write_json_report,
    write_text_report,
)
from .render import render_manifest_markdown

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--basename", required=True)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source evidence/report file. Repeatable or comma-separated.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-output-dir", default="")
    parser.add_argument("--chunk-max-chars", type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument("--chunk-overlap-lines", type=int, default=DEFAULT_CHUNK_OVERLAP_LINES)
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Disable local Ollama summaries. Ollama is enabled by default.",
    )
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--ollama-timeout-seconds", type=int, default=45)
    parser.add_argument("--ollama-max-input-chars", type=int, default=6000)
    parser.add_argument("--ollama-keep-alive", default="30m")
    parser.add_argument(
        "--zip-output",
        default="",
        help="Optional zip path containing manifest and chunk files.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_output_path(repo_root, args.output_dir)
    chunk_dir = (
        resolve_output_path(repo_root, args.chunk_output_dir)
        if args.chunk_output_dir
        else output_dir / f"{args.basename}_chunks"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for old_chunk in chunk_dir.glob("*.md"):
        old_chunk.unlink()

    warnings: list[str] = []
    errors: list[str] = []
    source_values = split_path_values(list(args.source or []))
    if not source_values:
        errors.append("no source files provided")
    sources: list[dict[str, Any]] = []
    seen_sources: set[Path] = set()
    for raw in source_values:
        path = resolve_output_path(repo_root, raw)
        if path in seen_sources:
            warnings.append(f"duplicate source skipped: {repo_rel(repo_root, path)}")
            continue
        seen_sources.add(path)
        if not path.exists() or not path.is_file():
            warnings.append(f"missing source skipped: {repo_rel(repo_root, path)}")
            continue
        sources.append(chunk_one_source(args, repo_root, path, chunk_dir, warnings))

    chunk_files = [chunk["chunk_file"] for source in sources for chunk in source.get("chunks", [])]
    duplicated_chunk_files = sorted({path for path in chunk_files if chunk_files.count(path) > 1})
    if duplicated_chunk_files:
        errors.append(f"duplicate chunk_file paths detected: {duplicated_chunk_files[:20]}")
    report = {
        "schema_version": 1,
        "kind": "semantic_evidence_chunk_manifest",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": True,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "ollama": {
            "enabled": not args.no_ollama,
            "model": args.ollama_model,
            "host": args.ollama_host,
            "mode": "local_direct_no_gpu_npu_audit",
            "disable_flag": "--no-ollama",
        },
        "chunking_policy": {
            "semantic_boundaries_first": True,
            "size_window_sections_enabled": True,
            "chunk_max_chars": args.chunk_max_chars,
            "chunk_overlap_lines": args.chunk_overlap_lines,
            "not_plain_truncation": True,
            "previous_next_links": True,
            "source_sha256_preserved": True,
        },
        "sources": sources,
        "chunk_files": chunk_files,
        "chunk_output_dir": repo_rel(repo_root, chunk_dir),
        "zip_output": None,
        "guardrails": {
            "report_only": True,
            "committable_location": "docs/LOCAL_VALIDATION_EVIDENCE",
            "raw_output_commit_allowed": False,
            "provider_execution_performed": False,
            "npu_audit_performed": False,
            "gpu_audit_performed": False,
        },
    }
    manifest_json = output_dir / f"{args.basename}_chunk_manifest.json"
    manifest_md = output_dir / f"{args.basename}_chunk_manifest.md"
    write_json_report(report, manifest_json)
    write_text_report(render_manifest_markdown(report), manifest_md)
    if args.zip_output:
        zip_path = resolve_output_path(repo_root, args.zip_output)
        zip_sources = [manifest_json, manifest_md] + [
            resolve_output_path(repo_root, path) for path in chunk_files
        ]
        report["zip_output"] = write_zip(zip_path, repo_root, zip_sources)
        write_json_report(report, manifest_json)
        write_text_report(render_manifest_markdown(report), manifest_md)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "manifest_json": str(manifest_json),
                "manifest_md": str(manifest_md),
                "chunk_count": len(chunk_files),
                "zip_output": report.get("zip_output"),
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2
