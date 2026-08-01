from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aicarmine_broker.helper import vulkan_helper
from aicarmine_broker.memory_tools import (
    planner_scratchpad_read,
    planner_scratchpad_write,
    runtime_sqlite_memory_cleanup,
    runtime_sqlite_memory_search,
    runtime_sqlite_memory_write,
)
from aicarmine_broker.repo_tools import (
    repo_ast_grep_dry_run,
    repo_ast_grep_search,
    repo_apply_patch,
    repo_capabilities,
    repo_command,
    repo_ctags_symbols,
    repo_fd_files,
    repo_git_apply_check,
    repo_hyperfine_benchmark,
    repo_jq_query,
    repo_list_files,
    repo_propose_code_edit,
    repo_pyright_check,
    repo_pytest_run,
    repo_read,
    repo_rg_search,
    repo_ruff_check,
    repo_search,
    repo_semantic_search,
    repo_semgrep_scan,
    repo_shellcheck,
    repo_status,
    repo_tree,
    repo_tree_sitter_parse,
    repo_unidiff_validate,
    repo_validate,
    repo_write_file,
    terminal_list_files,
    terminal_run_command_wait,
    terminal_search_files,
)
from aicarmine_broker.tool_contract import normalize_tool_name

from ..shared.diagnostics import diagnostic_row, safe_text


@dataclass(frozen=True)
class DispatchRequest:
    name: str
    args: dict[str, Any]
    root: Path
    allow_command: bool
    user_consent: str


ToolHandler = Callable[[DispatchRequest], dict[str, Any]]


@dataclass(frozen=True)
class BaseTool:
    name: str
    handler: ToolHandler

    def execute(self, request: DispatchRequest) -> dict[str, Any]:
        return self.handler(request)


class RegistryToolDispatcher:
    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = {normalize_tool_name(tool.name): tool for tool in tools}

    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def dispatch(self, request: DispatchRequest) -> dict[str, Any]:
        tool_name = normalize_tool_name(request.name)
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"ok": False, "tool": tool_name, "error": "unknown internal tool"}
        normalized_request = DispatchRequest(
            name=tool_name,
            args=dict(request.args or {}),
            root=request.root,
            allow_command=request.allow_command,
            user_consent=request.user_consent,
        )
        try:
            result = tool.execute(normalized_request)
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            return {
                "ok": False,
                "tool": tool_name,
                "error": "tool execution failed",
                "error_type": type(exc).__name__,
                "tool_dispatch_diagnostics": [
                    diagnostic_row(
                        "tool_handler_exception",
                        schema="tool_dispatch_diagnostic.v1",
                        exc=exc,
                        tool=tool_name,
                        root=safe_text(request.root, limit=500),
                    )
                ],
            }
        return result if isinstance(result, dict) else {
            "ok": False,
            "tool": tool_name,
            "error": "tool handler returned non-object result",
            "error_type": type(result).__name__,
            "tool_dispatch_diagnostics": [
                diagnostic_row(
                    "tool_handler_result_not_object",
                    schema="tool_dispatch_diagnostic.v1",
                    tool=tool_name,
                    result_type=type(result).__name__,
                    result_preview=safe_text(result, limit=500),
                )
            ],
        }


def _simple(handler: Callable[[dict[str, Any], Path], dict[str, Any]]) -> ToolHandler:
    return lambda request: handler(request.args, request.root)


def _command(
    handler: Callable[..., dict[str, Any]],
) -> ToolHandler:
    return lambda request: handler(
        request.args,
        request.root,
        allow_command=request.allow_command,
        user_consent=request.user_consent,
    )


def build_default_dispatcher() -> RegistryToolDispatcher:
    return RegistryToolDispatcher(
        [
            BaseTool("repo_capabilities", _simple(repo_capabilities)),
            BaseTool("repo_status", _simple(repo_status)),
            BaseTool("repo_tree", _simple(repo_tree)),
            BaseTool("repo_list_files", _simple(repo_list_files)),
            BaseTool("repo_search", _simple(repo_search)),
            BaseTool("repo_semantic_search", _simple(repo_semantic_search)),
            BaseTool("repo_fd_files", _simple(repo_fd_files)),
            BaseTool("repo_rg_search", _simple(repo_rg_search)),
            BaseTool("repo_jq_query", _simple(repo_jq_query)),
            BaseTool("repo_ast_grep_search", _simple(repo_ast_grep_search)),
            BaseTool("repo_ast_grep_dry_run", _simple(repo_ast_grep_dry_run)),
            BaseTool("repo_tree_sitter_parse", _simple(repo_tree_sitter_parse)),
            BaseTool("repo_unidiff_validate", _simple(repo_unidiff_validate)),
            BaseTool("repo_git_apply_check", _simple(repo_git_apply_check)),
            BaseTool("repo_ruff_check", _simple(repo_ruff_check)),
            BaseTool("repo_pyright_check", _simple(repo_pyright_check)),
            BaseTool("repo_pytest_run", _simple(repo_pytest_run)),
            BaseTool("repo_shellcheck", _simple(repo_shellcheck)),
            BaseTool("repo_ctags_symbols", _simple(repo_ctags_symbols)),
            BaseTool("repo_semgrep_scan", _simple(repo_semgrep_scan)),
            BaseTool("repo_hyperfine_benchmark", _command(repo_hyperfine_benchmark)),
            BaseTool("repo_read", _simple(repo_read)),
            BaseTool("repo_propose_code_edit", _simple(repo_propose_code_edit)),
            BaseTool("repo_apply_patch", _simple(repo_apply_patch)),
            BaseTool("repo_write_file", _simple(repo_write_file)),
            BaseTool("repo_validate", _simple(repo_validate)),
            BaseTool("repo_command", _command(repo_command)),
            BaseTool("terminal_list_files", _simple(terminal_list_files)),
            BaseTool("terminal_search_files", _simple(terminal_search_files)),
            BaseTool("terminal_run_command_wait", _command(terminal_run_command_wait)),
            BaseTool("planner_scratchpad_write", _simple(planner_scratchpad_write)),
            BaseTool("planner_scratchpad_read", _simple(planner_scratchpad_read)),
            BaseTool("runtime_sqlite_memory_search", _simple(runtime_sqlite_memory_search)),
            BaseTool("runtime_sqlite_memory_write", _simple(runtime_sqlite_memory_write)),
            BaseTool("runtime_sqlite_memory_cleanup", _command(runtime_sqlite_memory_cleanup)),
            BaseTool("vulkan_helper", _simple(vulkan_helper)),
        ]
    )
