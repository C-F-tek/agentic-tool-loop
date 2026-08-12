"""Repository tool inventory for Full0To10 capability manifests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import REQUIRED_TOOL_PATHS


def count_lines(path: Path) -> int | None:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").count("\n")


def build_tool_inventory(repo_root: Path) -> dict[str, Any]:
    tools = []
    missing = []
    for rel in REQUIRED_TOOL_PATHS:
        path = repo_root / rel
        exists = path.exists()
        if not exists:
            missing.append(rel)
        tools.append(
            {
                "path": rel,
                "exists": exists,
                "lines": count_lines(path),
                "git_trackable": True,
            }
        )
    return {
        "passed": not missing,
        "tool_count": len(tools),
        "missing": missing,
        "tools": tools,
    }
