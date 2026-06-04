from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import repo_rel, safe_rel_path
from aicarmine_broker.job_store import now, write_json


def repo_tree(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    max_files = max(1, min(int(args.get("max_files") or 200), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 3), 20))
    excluded_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        "output",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_tree",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {"ok": False, "tool": "repo_tree", "path": rel, "error": "path_not_found"}

    entries: list[dict[str, Any]] = []
    if base.is_file():
        entries.append({"path": repo_rel(base, LAB_REPO), "kind": "file", "size_bytes": base.stat().st_size})
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, files in os.walk(base):
            cp = Path(current)
            depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            if depth > max_depth:
                dirs[:] = []
                continue
            for dn in dirs:
                entries.append({"path": repo_rel(cp / dn, LAB_REPO), "kind": "dir"})
                if len(entries) >= max_files:
                    break
            for fn in files:
                p = cp / fn
                entries.append({"path": repo_rel(p, LAB_REPO), "kind": "file", "size_bytes": p.stat().st_size})
                if len(entries) >= max_files:
                    break
            if len(entries) >= max_files:
                break

    payload = {
        "ok": True,
        "tool": "repo_tree",
        "path": rel,
        "count": len(entries),
        "entries": entries,
        "truncated": len(entries) >= max_files,
    }
    artifact = root / "tool-results" / f"{now()}-repo_tree.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
