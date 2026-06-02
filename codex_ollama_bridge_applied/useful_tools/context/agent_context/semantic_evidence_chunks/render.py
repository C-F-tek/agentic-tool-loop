"""Chunk and manifest renderers."""

from __future__ import annotations

from typing import Any

def fence_for(text: str) -> str:
    return "````" if "```" in text else "```"

def render_chunk_file(
    *,
    source_rel: str,
    source_sha256: str | None,
    chunk: dict[str, Any],
    chunk_index: int,
    chunk_count: int,
    content: str,
    context_before: str,
    context_after: str,
    summary: str,
    summary_source: str,
    previous_file: str | None,
    next_file: str | None,
    language_hint: str,
) -> str:
    fence = fence_for(content)
    lines = [
        f"# Evidence Chunk {chunk_index:04d}/{chunk_count:04d}",
        "",
        f"- source: `{source_rel}`",
        f"- source_sha256: `{source_sha256}`",
        f"- line_start: `{chunk['line_start']}`",
        f"- line_end: `{chunk['line_end']}`",
        f"- section_kinds: `{chunk.get('section_kinds')}`",
        f"- previous_chunk_file: `{previous_file or ''}`",
        f"- next_chunk_file: `{next_file or ''}`",
        f"- summary_source: `{summary_source}`",
        "",
        "## Local chunk summary",
        "",
        summary,
        "",
    ]
    if context_before:
        lines.extend(["## Context before", "", context_before, ""])
    lines.extend(["## Chunk content", "", f"{fence}{language_hint}", content, fence, ""])
    if context_after:
        lines.extend(["## Context after", "", context_after, ""])
    return "\n".join(lines)

def render_manifest_markdown(report: dict[str, Any]) -> str:
    lines = ["# Semantic Evidence Chunk Manifest", ""]
    lines.append(f"- Passed: `{report.get('passed')}`")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(f"- Ollama enabled: `{report.get('ollama', {}).get('enabled')}`")
    lines.append(f"- Ollama model: `{report.get('ollama', {}).get('model')}`")
    lines.append(f"- Chunk files: `{len(report.get('chunk_files') or [])}`")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source in report.get("sources", []):
        lines.append(
            f"- `{source.get('path')}` chunks=`{source.get('chunk_count')}` lines=`{source.get('line_count')}` sha256=`{source.get('sha256')}`"
        )
        for chunk in source.get("chunks", [])[:20]:
            lines.append(
                f"  - `{chunk.get('chunk_file')}` lines `{chunk.get('line_start')}-{chunk.get('line_end')}` summary_source=`{chunk.get('summary_source')}`"
            )
        if len(source.get("chunks", [])) > 20:
            lines.append(f"  - ... {len(source.get('chunks', [])) - 20} more chunks")
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for warning in report.get("warnings", [])[:80]:
            lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)
