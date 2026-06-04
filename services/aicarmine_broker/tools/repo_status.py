from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO, REAL_REPO, VALID_INTERNAL_TOOLS
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tool_registry import capability_map
from aicarmine_broker.tools.powershell_runner import run_ps


def detect_stack() -> dict[str, Any]:
    excluded = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        "output",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    py_count = csproj_count = sln_count = 0
    for _, dirs, files in os.walk(LAB_REPO):
        dirs[:] = [d for d in dirs if d not in excluded]
        for filename in files:
            low = filename.lower()
            if low.endswith(".py"):
                py_count += 1
            elif low.endswith(".csproj"):
                csproj_count += 1
            elif low.endswith(".sln"):
                sln_count += 1
    canonical = ["git status --short --branch", "git diff --check"]
    if py_count:
        canonical.append("python -m compileall -q ia_carmine; python -m compileall -q Tools")
    if csproj_count or sln_count:
        canonical.append("dotnet build")
    if (LAB_REPO / "package.json").exists():
        canonical.append("type package.json")
    return {
        "lab_repo": str(LAB_REPO),
        "real_repo": str(REAL_REPO),
        "python_file_count": py_count,
        "csproj_count": csproj_count,
        "sln_count": sln_count,
        "canonical_commands": canonical,
    }


def repo_capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    registry = capability_map()
    capabilities = [
        {
            "name": "repo_capabilities",
            "risk": "read_only",
            "when_to_use": "Use when the model is unsure which repo/file/tool action to call next.",
            "required_args": [],
        },
        {
            "name": "repo_status",
            "risk": "read_only",
            "when_to_use": "Git status, branch, diff stat, changed files, diff --check and stack.",
            "required_args": [],
        },
        {
            "name": "repo_tree",
            "risk": "read_only",
            "when_to_use": "List files/directories under a repo-relative path.",
            "required_args": ["path"],
        },
        {
            "name": "repo_list_files",
            "risk": "read_only",
            "when_to_use": "List files by suffix/path/limit. Prefer over repo_search for glob-like requests.",
            "required_args": [],
        },
        {
            "name": "repo_search",
            "risk": "read_only",
            "when_to_use": "Find symbols, paths, functions, errors, TODO/FIXME in file content. Accepts query, pattern or symbol.",
            "required_args": ["query|pattern|symbol"],
        },
        {
            "name": "repo_read",
            "risk": "read_only",
            "when_to_use": "Read one or more repo-relative files when the path is known. Accepts path, paths, item or items.",
            "required_args": ["path|paths|items"],
        },
        {
            "name": "repo_apply_patch",
            "risk": "write_safe_guarded",
            "when_to_use": "Replace exact old_text with new_text in a known file.",
            "required_args": ["path", "old_text", "new_text"],
        },
        {
            "name": "repo_write_file",
            "risk": "write_safe_guarded",
            "when_to_use": "Create or overwrite small text files in LAB_REPO.",
            "required_args": ["path", "content"],
        },
        {
            "name": "repo_validate",
            "risk": "diagnostic",
            "when_to_use": "Run git diff --check and Python compile after any edit.",
            "required_args": [],
        },
        {
            "name": "repo_command",
            "risk": "diagnostic_or_write_guarded",
            "when_to_use": "Run safe validation commands. Dangerous commands require user_consent.",
            "required_args": ["command"],
        },
        {
            "name": "vulkan_helper",
            "risk": "composite_read_helper",
            "when_to_use": "Generic repo analysis, problem finding, patch planning.",
            "required_args": ["task"],
        },
    ]
    payload = {
        "ok": True,
        "tool": "repo_capabilities",
        "available_tools": capabilities,
        "valid_internal_tools": sorted(VALID_INTERNAL_TOOLS),
        "registry": registry,
        "contract": registry["runtime_contract"],
        "public_openwebui_surface": registry["surfaces"]["openwebui_public"],
        "internal_planner_surface": registry["surfaces"]["planner_internal"],
        "stack": detect_stack(),
        "input_args": args,
    }
    write_json(root / "tool-results" / f"{now()}-repo_capabilities.json", payload)
    return payload


def repo_status(args: dict[str, Any], root: Path) -> dict[str, Any]:
    commands = {
        "status": "git status --short --branch",
        "diff_stat": "git diff --stat HEAD",
        "diff_name_status": "git diff --name-status HEAD",
        "diff_check": "git diff --check",
        "branch": "git branch --show-current",
    }
    results: dict[str, Any] = {}
    for name, cmd in commands.items():
        result = run_ps(cmd, timeout=120)
        artifact = root / "commands" / f"{name}.json"
        write_json(artifact, {"command": cmd, "result": result})
        results[name] = {
            "command": cmd,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout_tail"],
            "stderr_tail": result["stderr_tail"],
            "artifact": str(artifact),
        }
    payload = {"ok": True, "tool": "repo_status", "stack": detect_stack(), "results": results}
    write_json(root / "tool-results" / f"{now()}-repo_status.json", payload)
    return payload
