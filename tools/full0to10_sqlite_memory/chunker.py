"""Text and Markdown chunking helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import MAX_CHUNK_CHARS

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    text: str
    heading_path: str
    chunk_index: int


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        start = end
    return chunks


def markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    headings: list[str] = []
    current: list[str] = []
    current_heading = ""
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            if current:
                sections.append((current_heading, "\n".join(current).strip()))
                current = []
            level = len(match.group(1))
            title = match.group(2).strip()
            headings = headings[: level - 1] + [title]
            current_heading = " > ".join(headings)
        current.append(line)
    if current:
        sections.append((current_heading, "\n".join(current).strip()))
    return sections or [("", text)]


def chunk_markdown(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    output: list[Chunk] = []
    for heading, section in markdown_sections(text):
        for part in split_text(section, max_chars=max_chars):
            output.append(Chunk(text=part, heading_path=heading, chunk_index=len(output)))
    return output


def chunk_plain(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    return [Chunk(text=part, heading_path="", chunk_index=i) for i, part in enumerate(split_text(text, max_chars))]
