from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO, parse_bool
from aicarmine_broker.infrastructure.filesystem_repo import repo_rel, safe_rel_path
from aicarmine_broker.job_store import now, write_json


_EXCLUDE_DIRS_DEFAULT = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        "output",
        "indexAI",
    }
)


def repo_list_files(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or ".").strip()
    suffix = str(args.get("suffix") or args.get("extension") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or args.get("max_files") or 20), 1000))
    max_depth = max(0, min(int(args.get("max_depth") or 50), 100))
    core = parse_bool(args.get("core", False), False)

    if core and path in {"", "."}:
        path = "ia_carmine"
    if core and not suffix:
        suffix = ".py"

    exclude_dirs = set(str(d) for d in (args.get("exclude_dirs") or []))
    exclude_dirs |= _EXCLUDE_DIRS_DEFAULT

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        base = (LAB_REPO / rel).resolve(strict=False)
        base.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_list_files",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not base.exists():
        return {"ok": False, "tool": "repo_list_files", "path": rel, "error": "path_not_found"}

    def _accept(fp: Path) -> bool:
        return not suffix or fp.suffix.lower() == suffix

    files: list[dict[str, Any]] = []
    if base.is_file():
        if _accept(base):
            files.append({"path": repo_rel(base, LAB_REPO), "size_bytes": base.stat().st_size})
    else:
        base_depth = len(base.relative_to(LAB_REPO).parts)
        for current, dirs, filenames in os.walk(base):
            cp = Path(current)
            depth = len(cp.relative_to(LAB_REPO).parts) - base_depth
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            if depth > max_depth:
                dirs[:] = []
                continue
            for fn in filenames:
                fp = cp / fn
                if _accept(fp):
                    files.append({"path": repo_rel(fp, LAB_REPO), "size_bytes": fp.stat().st_size})

    files = sorted(files, key=lambda x: str(x.get("path") or "").lower())
    selected = files[:limit]
    payload = {
        "ok": True,
        "tool": "repo_list_files",
        "path": rel if path not in {"", "."} else ".",
        "suffix": suffix,
        "core": core,
        "limit": limit,
        "count": len(selected),
        "total_matches": len(files),
        "files": selected,
        "paths": [str(x["path"]) for x in selected],
        "truncated": len(files) > limit,
    }
    artifact = root / "tool-results" / f"{now()}-repo_list_files.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
