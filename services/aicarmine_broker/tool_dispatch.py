"""Deterministic internal tool dispatch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .helper import vulkan_helper
from .memory_tools import (
    planner_scratchpad_read,
    planner_scratchpad_write,
    runtime_sqlite_memory_cleanup,
    runtime_sqlite_memory_search,
    runtime_sqlite_memory_write,
)
from .repo_tools import (
    repo_apply_patch,
    repo_capabilities,
    repo_command,
    repo_list_files,
    repo_propose_code_edit,
    repo_read,
    repo_search,
    repo_status,
    repo_tree,
    repo_validate,
    repo_write_file,
    terminal_list_files,
    terminal_run_command_wait,
    terminal_search_files,
)
from .tool_contract import normalize_tool_name


def dispatch_tool(name: str, args: dict[str, Any], root: Path, allow_command: bool, user_consent: str) -> dict[str, Any]:
    tool = normalize_tool_name(name)
    if tool == 'repo_capabilities':
        return repo_capabilities(args, root)
    if tool == 'repo_status':
        return repo_status(args, root)
    if tool == 'repo_tree':
        return repo_tree(args, root)
    if tool == 'repo_list_files':
        return repo_list_files(args, root)
    if tool == 'repo_search':
        return repo_search(args, root)
    if tool == 'repo_read':
        return repo_read(args, root)
    if tool == 'repo_propose_code_edit':
        return repo_propose_code_edit(args, root)
    if tool == 'repo_apply_patch':
        return repo_apply_patch(args, root)
    if tool == 'repo_write_file':
        return repo_write_file(args, root)
    if tool == 'repo_validate':
        return repo_validate(args, root)
    if tool == 'repo_command':
        return repo_command(args, root, allow_command=allow_command, user_consent=user_consent)
    if tool == 'terminal_list_files':
        return terminal_list_files(args, root)
    if tool == 'terminal_search_files':
        return terminal_search_files(args, root)
    if tool == 'terminal_run_command_wait':
        return terminal_run_command_wait(args, root, allow_command=allow_command, user_consent=user_consent)
    if tool == 'planner_scratchpad_write':
        return planner_scratchpad_write(args, root)
    if tool == 'planner_scratchpad_read':
        return planner_scratchpad_read(args, root)
    if tool == 'runtime_sqlite_memory_search':
        return runtime_sqlite_memory_search(args, root)
    if tool == 'runtime_sqlite_memory_write':
        return runtime_sqlite_memory_write(args, root)
    if tool == 'runtime_sqlite_memory_cleanup':
        return runtime_sqlite_memory_cleanup(args, root)
    if tool == 'vulkan_helper':
        return vulkan_helper(args, root)
    return {'ok': False, 'tool': tool, 'error': 'unknown internal tool'}
