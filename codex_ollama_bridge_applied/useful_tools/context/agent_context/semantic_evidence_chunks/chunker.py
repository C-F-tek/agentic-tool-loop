"""Source chunking workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .common import read_text, repo_rel, sha256_file, sha256_text, slugify
from .render import render_chunk_file
from .sections import detect_sections, normalize_sections, pack_sections, section_text
from .summary import call_ollama_summary, deterministic_summary

def chunk_one_source(
    args: argparse.Namespace,
    repo_root: Path,
    source_path: Path,
    chunk_dir: Path,
    warnings: list[str],
) -> dict[str, Any]:
    text, error = read_text(source_path)
    rel = repo_rel(repo_root, source_path)
    if error:
        return {
            "path": rel,
            "exists": source_path.exists(),
            "ok": False,
            "error": error,
            "chunks": [],
        }
    lines = text.splitlines()
    sections = detect_sections(source_path, text, int(args.chunk_max_chars))
    sections = normalize_sections(lines, sections, int(args.chunk_max_chars))
    chunks = pack_sections(lines, sections, int(args.chunk_max_chars))
    source_sha = sha256_file(source_path)
    suffix_slug = source_path.suffix.lower().lstrip(".") or "txt"
    sha_slug = (source_sha or "nosha")[:12]
    stem_slug = slugify(Path(rel).stem, "source")[:58]
    source_slug = slugify(f"{stem_slug}_{suffix_slug}_{sha_slug}", "source")
    chunk_entries: list[dict[str, Any]] = []
    language_hint = source_path.suffix.lower().lstrip(".") or "text"
    pending_files: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_file = chunk_dir / f"{source_slug}_chunk_{idx:04d}.md"
        pending_files.append(repo_rel(repo_root, chunk_file))
    for idx, chunk in enumerate(chunks, start=1):
        start = int(chunk["line_start"])
        end = int(chunk["line_end"])
        content = section_text(lines, start, end)
        before_start = max(1, start - int(args.chunk_overlap_lines))
        after_end = min(len(lines), end + int(args.chunk_overlap_lines))
        context_before = (
            section_text(lines, before_start, start - 1) if before_start < start else ""
        )
        context_after = section_text(lines, end + 1, after_end) if end < after_end else ""
        summary_source = "deterministic"
        summary = deterministic_summary(content, list(chunk.get("section_titles") or []))
        ollama_elapsed = 0.0
        ollama_error = None
        if not args.no_ollama:
            generated, ollama_error, ollama_elapsed = call_ollama_summary(
                host=args.ollama_host,
                model=args.ollama_model,
                text=content,
                titles=list(chunk.get("section_titles") or []),
                timeout=int(args.ollama_timeout_seconds),
                max_input_chars=int(args.ollama_max_input_chars),
                keep_alive=args.ollama_keep_alive,
            )
            if generated:
                summary = generated
                summary_source = "ollama"
            elif ollama_error:
                warnings.append(
                    f"{rel} chunk {idx}: Ollama summary unavailable; deterministic summary retained: {ollama_error}"
                )
        previous_file = pending_files[idx - 2] if idx > 1 else None
        next_file = pending_files[idx] if idx < len(pending_files) else None
        chunk_file = chunk_dir / f"{source_slug}_chunk_{idx:04d}.md"
        chunk_text = render_chunk_file(
            source_rel=rel,
            source_sha256=source_sha,
            chunk=chunk,
            chunk_index=idx,
            chunk_count=len(chunks),
            content=content,
            context_before=context_before,
            context_after=context_after,
            summary=summary,
            summary_source=summary_source,
            previous_file=previous_file,
            next_file=next_file,
            language_hint=language_hint,
        )
        chunk_file.write_text(chunk_text, encoding="utf-8", newline="\n")
        chunk_entries.append(
            {
                "chunk_id": f"{rel}#L{start}-L{end}",
                "chunk_file": repo_rel(repo_root, chunk_file),
                "source_path": rel,
                "source_sha256": source_sha,
                "line_start": start,
                "line_end": end,
                "raw_chars": len(content),
                "chunk_sha256": sha256_text(chunk_text),
                "summary": summary,
                "summary_source": summary_source,
                "ollama_elapsed_seconds": ollama_elapsed,
                "ollama_error": ollama_error,
                "previous_chunk_file": previous_file,
                "next_chunk_file": next_file,
                "section_titles": chunk.get("section_titles") or [],
                "section_kinds": chunk.get("section_kinds") or [],
            }
        )
    return {
        "path": rel,
        "exists": source_path.exists(),
        "ok": True,
        "size_bytes": source_path.stat().st_size if source_path.exists() else None,
        "line_count": len(lines),
        "sha256": source_sha,
        "chunk_count": len(chunk_entries),
        "chunks": chunk_entries,
    }
