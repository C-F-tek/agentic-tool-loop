"""I/O helpers for Full0To10 quality stack."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def latest_matching(root: Path, name: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted(root.rglob(name), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
