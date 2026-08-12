"""Markdown heading splitter and safe slug helpers."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .constants import MAX_SLUG_CHARS

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SAFE_CHARS_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    text: str
    index: int


def compact_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:10]


def slugify(title: str, max_chars: int = MAX_SLUG_CHARS) -> str:
    raw = title.lower().replace("\\", "-").replace("/", "-")
    raw = raw.replace(":", "-").replace("*", "-").replace("?", "-")
    raw = raw.replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-")
    raw = SAFE_CHARS_RE.sub("-", raw)
    while "--" in raw:
        raw = raw.replace("--", "-")
    raw = raw.strip("-._ ")
    if not raw:
        raw = "section"
    digest = compact_hash(title)
    budget = max(16, max_chars - len(digest) - 1)
    trimmed = raw[:budget].strip("-._ ") or "section"
    return f"{trimmed}-{digest}"


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current: list[str] = []
    title = "Overview"
    level = 1
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match and current:
            sections.append(Section(title=title, level=level, text="\n".join(current).strip() + "\n", index=len(sections)))
            current = []
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
        current.append(line)
    if current:
        sections.append(Section(title=title, level=level, text="\n".join(current).strip() + "\n", index=len(sections)))
    return sections or [Section(title="Overview", level=1, text=text, index=0)]
