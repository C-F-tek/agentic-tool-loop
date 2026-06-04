"""
aicarmine_broker.repo_tools
============================
All deterministic local repository tools executed by the 3572 dispatcher:

    repo_capabilities, repo_status, repo_tree, repo_list_files,
    repo_search, repo_read, repo_apply_patch, repo_write_file,
    repo_validate, repo_command, vulkan_helper

Each function takes ``(args: dict, root: Path)`` and returns a result dict.
No HTTP calls are made here.  ``run_ps`` is the only subprocess boundary.
"""
from __future__ import annotations

from typing import Any

from .config import (
    COMMAND_TIMEOUT_SECONDS,
    MAX_TOOL_RESULT_CHARS,
)
from .infrastructure.result_compaction import compact as _compact
from .infrastructure.filesystem_repo import safe_rel_path
from .tools.command_safety import dangerous_command
from .tools.repo_deterministic import (
    repo_ast_grep_dry_run,
    repo_ast_grep_search,
    repo_ctags_symbols,
    repo_fd_files,
    repo_git_apply_check,
    repo_hyperfine_benchmark,
    repo_jq_query,
    repo_pyright_check,
    repo_pytest_run,
    repo_rg_search,
    repo_ruff_check,
    repo_semgrep_scan,
    repo_shellcheck,
    repo_tree_sitter_parse,
    repo_unidiff_validate,
)
from .tools.powershell_runner import run_ps as _tool_run_ps
from .tools.repo_code_product import repo_propose_code_edit
from .tools.repo_command import repo_command
from .tools.repo_list_files import repo_list_files
from .tools.repo_patch import repo_apply_patch, repo_write_file
from .tools.repo_read import repo_read
from .tools.repo_search import repo_search
from .tools.repo_status import detect_stack, repo_capabilities, repo_status
from .tools.repo_tree import repo_tree
from .tools.repo_validate import repo_validate
from .tools.terminal import (
    normalize_terminal_path,
    terminal_environment_contract,
    terminal_list_files,
    terminal_preferred_cwd,
    terminal_run_command_wait,
    terminal_search_files,
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def run_ps(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    return _tool_run_ps(command, timeout=timeout)


def compact(value: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    return _compact(value, limit)


# ---------------------------------------------------------------------------
# Tool: deterministic external adapters
# ---------------------------------------------------------------------------

# Implementations live in aicarmine_broker.tools.repo_deterministic.
