"""JSON reader for repo quality packet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import MAX_PREVIEW_CHARS
from .paths import repo_relative


def read_json_file(repo_root: Path, path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        data = json.loads(text)
        valid = True
        error = None
        keys = list(data.keys())[:40] if isinstance(data, dict) else []
        data_type = type(data).__name__
    except Exception as exc:
        valid = False
        error = str(exc)
        keys = []
        data_type = "invalid"
    return {
        "path": repo_relative(path, repo_root),
        "kind": "json",
        "json_valid": valid,
        "json_error": error,
        "json_type": data_type,
        "top_keys": keys,
        "line_count": text.count("\n") + 1,
        "preview": text[:MAX_PREVIEW_CHARS],
    }
