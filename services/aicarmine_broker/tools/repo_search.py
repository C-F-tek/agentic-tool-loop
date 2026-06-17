from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import json

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.command_safety import classify_command
from aicarmine_broker.tools.powershell_runner import run_ps as _run_ps


def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(
        args.get("query")
        or args.get("pattern")
        or args.get("symbol")
        or args.get("needle")
        or args.get("text")
        or ""
    ).strip()
    if re.fullmatch(r"\*\.[A-Za-z0-9_]+", query.strip()):
        suggested_path = str(args.get("path") or ".").strip() or "."
        return {
            "ok": False,
            "tool": "repo_search",
            "error": "glob_pattern_is_not_text_search",
            "query": query,
            "hint": "Use repo_list_files with suffix instead of repo_search for glob-like file listing.",
            "suggested_next_actions": [
                {
                    "tool": "repo_list_files",
                    "argument_hints": {
                        "path": suggested_path,
                        "suffix": query.strip()[1:],
                        "limit": 20,
                    },
                    "reason": "glob_pattern_is_file_listing_not_text_search",
                    "not_runnable_without_path_validation": False,
                }
            ],
        }
    if not query:
        return {"ok": False, "tool": "repo_search", "error": "missing query"}

    mode = str(args.get("mode") or "rg").strip()
    path = str(args.get("path") or ".").strip()
    try:
        max_results = min(1000, max(1, int(args.get("max_results") or args.get("limit") or 80)))
    except (TypeError, ValueError, OverflowError):
        max_results = 80

    try:
        rel = "." if path in {"", "."} else safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_search",
            "path": path,
            "error": "invalid_repo_path",
            "error_type": type(exc).__name__,
            "detail": str(exc),
        }

    q = json.dumps(query)
    target = str(full)
    if mode == "git_grep":
        command = f"git grep -n -- {q}"
    elif mode == "fd":
        command = f"fd {q} {target}"
    else:
        command = (
            f"rg -n --hidden --glob '!**/__pycache__/**' "
            f"--glob '!output/**' {q} {target}"
        )

    classification = classify_command(command)
    result = _run_ps(command, timeout=120)
    payload = {
        "ok": result["returncode"] in (0, 1),
        "tool": "repo_search",
        "mode": mode,
        "query": query,
        "command": command,
        "command_class": classification.command_class,
        "consent_required": classification.consent_required,
        "policy": classification.reason,
        "returncode": result["returncode"],
        "matches": result["stdout"].splitlines()[:max_results],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = root / "tool-results" / f"{now()}-repo_search.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
