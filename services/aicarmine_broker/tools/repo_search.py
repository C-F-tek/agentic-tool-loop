from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aicarmine_broker.application.shared.tool_result import ToolResult
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
        raw_suggested_path = str(args.get("path") or ".").strip() or "."
        try:
            suggested_rel = (
                "."
                if raw_suggested_path in {"", "."}
                else safe_rel_path(raw_suggested_path)
            )
            suggested_full = (LAB_REPO / suggested_rel).resolve(strict=False)
            suggested_full.relative_to(LAB_REPO)
        except Exception:
            suggested_rel = "."
        result = ToolResult.error_result(
            tool="repo_search",
            error="glob_pattern_is_not_text_search",
            hint="Use repo_list_files with suffix instead of repo_search for glob-like file listing.",
            query=query,
            suggested_next_actions=[
                {
                    "tool": "repo_list_files",
                    "argument_hints": {
                        "path": suggested_rel,
                        "suffix": query.strip()[1:],
                        "limit": 20,
                    },
                    "reason": "glob_pattern_is_file_listing_not_text_search",
                    "not_runnable_without_path_validation": True,
                }
            ],
        )
        return asdict(result)

    if not query:
        result = ToolResult.error_result(tool="repo_search", error="missing query")
        return asdict(result)

    requested_mode = str(args.get("mode") or "rg").strip().lower()
    mode = requested_mode

    if mode not in {"rg", "git_grep", "fd"}:
        mode = "rg"
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
    target_q = json.dumps(target)
    rel_q = json.dumps(rel)
    if mode == "git_grep":
        command = f"git grep -n -- {q} -- {rel_q}"
    elif mode == "fd":
        command = f"fd {q} {target_q}"
    else:
        command = (
            f"rg -n --hidden --glob '!**/__pycache__/**' "
            f"--glob '!output/**' {q} {target_q}"
        )

    classification = classify_command(command)
    ps_result = _run_ps(command, timeout=120)
    if mode in {"rg", "git_grep"}:
        ok = ps_result["returncode"] in (0, 1)
        no_matches = ps_result["returncode"] == 1
    else:
        ok = ps_result["returncode"] == 0
        no_matches = ok and not ps_result["stdout"].strip()

    # Build structured result using ToolResult dataclass
    tool_result = ToolResult.ok_result(
        tool="repo_search",
        mode=mode,
        requested_mode=requested_mode,
        mode_defaulted=(mode != requested_mode),
        no_matches=no_matches,
        query=query,
        command=command,
        command_class=classification.command_class,
        consent_required=classification.consent_required,
        policy=classification.reason,
        returncode=ps_result["returncode"],
        matches=ps_result["stdout"].splitlines()[:max_results],
        stderr_tail=ps_result["stderr_tail"],
        path=rel,
        target=target,
    )
    artifact = root / "tool-results" / f"{now()}-repo_search.json"
    write_json(artifact, asdict(tool_result))
    result_dict = asdict(tool_result)
    result_dict["artifact"] = str(artifact)
    return result_dict
