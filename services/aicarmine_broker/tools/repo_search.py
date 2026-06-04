from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import json

from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.powershell_runner import run_ps as _run_ps


def repo_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if re.fullmatch(r"\*\.[A-Za-z0-9_]+", query.strip()):
        return {
            "ok": False,
            "tool": "repo_search",
            "error": "glob_pattern_is_not_text_search",
            "query": query,
            "hint": "Use repo_list_files with suffix instead of repo_search for glob-like file listing.",
            "suggested_tool": "repo_list_files",
            "suggested_arguments": {
                "path": "ia_carmine",
                "suffix": query.strip()[1:],
                "limit": 20,
                "core": True,
            },
        }
    if not query:
        return {"ok": False, "tool": "repo_search", "error": "missing query"}

    mode = str(args.get("mode") or "rg").strip()
    path = str(args.get("path") or ".").strip()
    max_results = max(1, min(int(args.get("max_results") or 80), 200))

    q = json.dumps(query)
    target = json.dumps(path)
    if mode == "git_grep":
        command = f"git grep -n -- {q}"
    elif mode == "fd":
        command = f"fd {q} {target}"
    else:
        command = (
            f"rg -n --hidden --glob '!**/__pycache__/**' "
            f"--glob '!output/**' {q} {target}"
        )

    result = _run_ps(command, timeout=120)
    payload = {
        "ok": result["returncode"] in (0, 1),
        "tool": "repo_search",
        "mode": mode,
        "query": query,
        "command": command,
        "returncode": result["returncode"],
        "matches": result["stdout"].splitlines()[:max_results],
        "stderr_tail": result["stderr_tail"],
    }
    artifact = root / "tool-results" / f"{now()}-repo_search.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
