"""Markdown reader for repo quality packet."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import MAX_PREVIEW_CHARS
from .paths import repo_relative


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def read_markdown(repo_root: Path, path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    headings = [{"level": len(m.group(1)), "title": m.group(2).strip()} for m in HEADING_RE.finditer(text)]
    lowered = text.lower()
    return {
        "path": repo_relative(path, repo_root),
        "kind": "markdown",
        "line_count": text.count("\n") + 1,
        "heading_count": len(headings),
        "headings": headings[:30],
        "mentions": {
            "full0to10": "full0to10" in lowered,
            "sqlite": "sqlite" in lowered,
            "provider": "provider" in lowered,
            "gpu": "gpu" in lowered,
            "npu": "npu" in lowered,
            "quality": "quality" in lowered,
        },
        "preview": text[:MAX_PREVIEW_CHARS],
    }
