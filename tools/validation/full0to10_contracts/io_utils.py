"""I/O helpers for Full0To10 contract validation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - diagnostics must serialize failures.
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, "top-level JSON is not an object"
    return data, None


def iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield item
            yield from iter_values(item)
    elif isinstance(value, list):
        for item in value:
            yield item
            yield from iter_values(item)


def normalize_path_like(text: str) -> str:
    return text.strip().replace("\\", "/")
