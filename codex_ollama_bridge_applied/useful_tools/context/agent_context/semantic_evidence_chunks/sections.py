"""Semantic section detection and packing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

def markdown_sections(lines: list[str]) -> list[dict[str, Any]]:
    headings: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((idx, match.group(2).strip()))
    if not headings:
        return []
    sections: list[dict[str, Any]] = []
    for pos, (start, title) in enumerate(headings):
        end = headings[pos + 1][0] - 1 if pos + 1 < len(headings) else len(lines)
        if start <= end:
            sections.append(
                {
                    "line_start": start,
                    "line_end": end,
                    "title": title,
                    "kind": "markdown_heading_section",
                }
            )
    return sections

def json_sections(lines: list[str]) -> list[dict[str, Any]]:
    anchors: list[tuple[int, str]] = []
    pattern = re.compile(r'^\s{0,4}"([A-Za-z0-9_.$-]{2,120})"\s*:\s*([\[{"0-9tfn-]|$)')
    for idx, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if match:
            key = match.group(1)
            if key not in {"path", "id", "kind", "passed", "errors", "warnings"}:
                anchors.append((idx, key))
    if not anchors:
        return []
    sections: list[dict[str, Any]] = []
    for pos, (start, key) in enumerate(anchors):
        end = anchors[pos + 1][0] - 1 if pos + 1 < len(anchors) else len(lines)
        if start <= end:
            sections.append(
                {
                    "line_start": start,
                    "line_end": end,
                    "title": key,
                    "kind": "json_key_section",
                }
            )
    return sections

def size_window_sections(lines: list[str], max_chars: int) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    start = 1
    current_chars = 0
    for idx, line in enumerate(lines, start=1):
        current_chars += len(line) + 1
        if current_chars >= max_chars and idx >= start:
            sections.append(
                {
                    "line_start": start,
                    "line_end": idx,
                    "title": f"lines {start}-{idx}",
                    "kind": "size_window_section",
                }
            )
            start = idx + 1
            current_chars = 0
    if start <= len(lines):
        sections.append(
            {
                "line_start": start,
                "line_end": len(lines),
                "title": f"lines {start}-{len(lines)}",
                "kind": "size_window_section",
            }
        )
    return sections

def detect_sections(path: Path, text: str, max_chars: int) -> list[dict[str, Any]]:
    lines = text.splitlines()
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        sections = markdown_sections(lines)
    elif suffix == ".json":
        sections = json_sections(lines)
    else:
        sections = []
    if not sections:
        return size_window_sections(lines, max_chars)
    return sections

def section_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])

def split_large_section(
    lines: list[str], section: dict[str, Any], max_chars: int
) -> list[dict[str, Any]]:
    start = int(section["line_start"])
    end = int(section["line_end"])
    out: list[dict[str, Any]] = []
    current_start = start
    current_chars = 0
    for idx in range(start, end + 1):
        current_chars += len(lines[idx - 1]) + 1
        if current_chars >= max_chars and idx >= current_start:
            out.append(
                {
                    "line_start": current_start,
                    "line_end": idx,
                    "title": section["title"],
                    "kind": section["kind"] + "_split",
                }
            )
            current_start = idx + 1
            current_chars = 0
    if current_start <= end:
        out.append(
            {
                "line_start": current_start,
                "line_end": end,
                "title": section["title"],
                "kind": section["kind"] + ("_split" if len(out) else ""),
            }
        )
    return out

def normalize_sections(
    lines: list[str], sections: list[dict[str, Any]], max_chars: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in sections:
        text = section_text(lines, int(section["line_start"]), int(section["line_end"]))
        if len(text) > max_chars:
            out.extend(split_large_section(lines, section, max_chars))
        else:
            out.append(section)
    return out

def pack_sections(
    lines: list[str], sections: list[dict[str, Any]], max_chars: int
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for section in sections:
        text = section_text(lines, int(section["line_start"]), int(section["line_end"]))
        extra = len(text) + 1
        if current and current_chars + extra > max_chars:
            chunks.append(build_chunk_from_sections(current))
            current = []
            current_chars = 0
        current.append(section)
        current_chars += extra
    if current:
        chunks.append(build_chunk_from_sections(current))
    return chunks

def build_chunk_from_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    start = min(int(item["line_start"]) for item in sections)
    end = max(int(item["line_end"]) for item in sections)
    titles = [str(item.get("title") or "") for item in sections if item.get("title")]
    kinds = sorted({str(item.get("kind") or "section") for item in sections})
    return {
        "line_start": start,
        "line_end": end,
        "section_titles": titles[:12],
        "section_kinds": kinds,
    }
