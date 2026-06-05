"""Generic text compaction primitives."""
from __future__ import annotations

import json
from typing import Any


def compact(value: Any, limit: int) -> str:
    text = (
        json.dumps(value, ensure_ascii=False, indent=2, default=str)
        if not isinstance(value, str)
        else value
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:limit] + ("\n... <truncated>" if len(text) > limit else "")
