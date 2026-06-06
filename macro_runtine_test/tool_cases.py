from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCase:
    tool: str
    request: str
    args: dict[str, Any] = field(default_factory=dict)
    approval_mode: str = "safe_write_lab"
    user_consent: str = ""
    max_steps: int = 8
    expect_tool_call: bool = True


def _base(
    tool: str,
    request: str,
    *,
    args: dict[str, Any] | None = None,
    approval_mode: str = "safe_write_lab",
    user_consent: str = "",
    max_steps: int = 8,
) -> ToolCase:
    return ToolCase(
        tool=tool,
        request=request,
        args=dict(args or {}),
        approval_mode=approval_mode,
        user_consent=user_consent,
        max_steps=max_steps,
    )


def build_tool_cases(*, sample_file: str, sample_files: tuple[str, ...], seed: int, run_id: str = "") -> dict[str, ToolCase]:
    second_file = sample_files[1] if len(sample_files) > 1 else sample_file
    suffix = str(run_id or seed).replace(" ", "-").replace(":", "-")
    test_path = f"macro-runtime-test-{suffix}.txt"
    patch_text = (
        f"diff --git a/{test_path} b/{test_path}\n"
        "new file mode 100644\n"
        "index 0000000..e69de29\n"
        "--- /dev/null\n"
        f"+++ b/{test_path}\n"
        "@@ -0,0 +1,2 @@\n"
        f"+macro runtime payload test seed {seed}\n"
        "+created by repo_apply_patch macro case\n"
    )
    small_unidiff = (
        f"diff --git a/{test_path} b/{test_path}\n"
        "--- a/{test_path}\n"
        f"+++ b/{test_path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    return {
        "repo_capabilities": _base(
            "repo_capabilities",
            "Use repo_capabilities and return the available internal tool surface.",
        ),
        "repo_status": _base("repo_status", "Use repo_status to read git status and diff summary."),
        "repo_tree": _base(
            "repo_tree",
            "Use repo_tree to list the repository root with a small depth.",
            args={"path": ".", "max_depth": 2, "limit": 80},
        ),
        "repo_list_files": _base(
            "repo_list_files",
            "Use repo_list_files to list a bounded set of files in the repository.",
            args={"path": ".", "limit": 80},
        ),
        "repo_search": _base(
            "repo_search",
            "Use repo_search with the target query from MACRO_TARGET_CONTEXT_JSON.",
            args={"query": "def", "limit": 20},
        ),
        "repo_fd_files": _base(
            "repo_fd_files",
            "Use repo_fd_files to find Python, Markdown or PowerShell files.",
            args={"query": "*.py", "limit": 40},
        ),
        "repo_rg_search": _base(
            "repo_rg_search",
            "Use repo_rg_search to search for the word import or function definitions.",
            args={"query": "import|def|class", "path": ".", "limit": 40},
        ),
        "repo_jq_query": _base(
            "repo_jq_query",
            "Use repo_jq_query on a tiny JSON object to verify jq payload handling.",
            args={"json": {"macro": True, "seed": seed}, "query": ".macro"},
        ),
        "repo_ast_grep_search": _base(
            "repo_ast_grep_search",
            "Use repo_ast_grep_search on the exact target path from explicit_request_context.",
            args={"path": sample_file, "pattern": "def $FUNC($$$ARGS): $$$BODY", "language": "python"},
        ),
        "repo_ast_grep_dry_run": _base(
            "repo_ast_grep_dry_run",
            "Use repo_ast_grep_dry_run on the exact target path from explicit_request_context.",
            args={"path": sample_file, "pattern": "def $FUNC($$$ARGS): $$$BODY", "language": "python"},
        ),
        "repo_tree_sitter_parse": _base(
            "repo_tree_sitter_parse",
            "Use repo_tree_sitter_parse on the exact target path from explicit_request_context.",
            args={"path": sample_file, "max_nodes": 120},
        ),
        "repo_unidiff_validate": _base(
            "repo_unidiff_validate",
            "Use repo_unidiff_validate against a small synthetic unified diff.",
            args={"unified_diff": small_unidiff},
        ),
        "repo_git_apply_check": _base(
            "repo_git_apply_check",
            "Use repo_git_apply_check against a small synthetic patch.",
            args={"patch": patch_text},
        ),
        "repo_ruff_check": _base(
            "repo_ruff_check",
            "Use repo_ruff_check on the current repository or report a typed missing-tool result.",
            args={"paths": [sample_file], "limit": 80},
        ),
        "repo_pyright_check": _base(
            "repo_pyright_check",
            "Use repo_pyright_check in bounded mode or report a typed missing-tool result.",
            args={"paths": [sample_file], "limit": 80},
        ),
        "repo_pytest_run": _base(
            "repo_pytest_run",
            "Use repo_pytest_run for a very small targeted collection/check if available.",
            args={"paths": ["tests/test_tool_dispatcher_contract.py"], "args": ["-q"], "timeout_seconds": 60},
        ),
        "repo_shellcheck": _base(
            "repo_shellcheck",
            "Use repo_shellcheck on PowerShell/shell files if applicable or return typed unavailable result.",
            args={"paths": [sample_file], "limit": 40},
        ),
        "repo_ctags_symbols": _base(
            "repo_ctags_symbols",
            "Use repo_ctags_symbols on the exact target path from explicit_request_context or return typed unavailable result.",
            args={"path": sample_file, "limit": 80},
        ),
        "repo_semgrep_scan": _base(
            "repo_semgrep_scan",
            "Use repo_semgrep_scan on the exact target path from explicit_request_context in bounded mode or return typed unavailable result.",
            args={"paths": [sample_file], "limit": 80},
        ),
        "repo_hyperfine_benchmark": _base(
            "repo_hyperfine_benchmark",
            "Use repo_hyperfine_benchmark with a trivial command or return typed unavailable result.",
            args={"command": "python --version", "runs": 1},
            user_consent="confirm benchmark",
        ),
        "repo_read": _base(
            "repo_read",
            "Use repo_read to read the full content of the exact target path from explicit_request_context.",
            args={"path": sample_file, "max_chars": 20000},
        ),
        "repo_propose_code_edit": _base(
            "repo_propose_code_edit",
            "Use repo_propose_code_edit report-only for the exact target path from explicit_request_context; do not write files.",
            args={
                "target_file": sample_file,
                "edit_kind": "unified_diff",
                "rationale": "macro runtime payload report-only edit proposal",
                "old_text": "",
                "new_text": "",
            },
            max_steps=10,
        ),
        "repo_apply_patch": _base(
            "repo_apply_patch",
            "Use repo_apply_patch to apply the small patch from explicit_request_context in the live lab repo.",
            args={"patch": patch_text, "apply": True},
            user_consent="confirm apply patch in lab repo",
        ),
        "repo_write_file": _base(
            "repo_write_file",
            "Use repo_write_file to write the tiny macro runtime test file described in explicit_request_context.",
            args={
                "path": test_path,
                "content": f"macro runtime payload test seed {seed}\n",
                "overwrite": True,
            },
            user_consent="confirm write file in lab repo",
        ),
        "repo_validate": _base(
            "repo_validate",
            "Use repo_validate for a bounded validation summary.",
            args={"paths": [sample_file, second_file], "limit": 80},
        ),
        "repo_command": _base(
            "repo_command",
            "Use repo_command to run a validation/read-only command inside the lab repo.",
            args={"command": "git status --short", "timeout_seconds": 60},
        ),
        "terminal_run_command_wait": _base(
            "terminal_run_command_wait",
            "Use terminal_run_command_wait to run a safe PowerShell location command.",
            args={"command": "(Get-Location).Path", "timeout_seconds": 30},
        ),
        "terminal_search_files": _base(
            "terminal_search_files",
            "Use terminal_search_files to search the lab repo for a common code term.",
            args={"query": "def", "content": True, "limit": 20},
        ),
        "terminal_list_files": _base(
            "terminal_list_files",
            "Use terminal_list_files to list the lab repo root.",
            args={"path": ".", "limit": 40},
        ),
        "planner_scratchpad_read": _base(
            "planner_scratchpad_read",
            "Use planner_scratchpad_read for macro runtime test scratchpad state.",
            args={"kind": "macro_runtime_test", "tag": f"seed-{seed}", "limit": 5},
        ),
        "planner_scratchpad_write": _base(
            "planner_scratchpad_write",
            "Use planner_scratchpad_write to store a tiny macro runtime diagnostic note.",
            args={"kind": "macro_runtime_test", "tag": f"seed-{seed}", "text": "macro runtime diagnostic note"},
        ),
        "runtime_sqlite_memory_search": _base(
            "runtime_sqlite_memory_search",
            "Use runtime_sqlite_memory_search for a macro runtime marker.",
            args={"query": "macro runtime payload", "limit": 5},
        ),
        "runtime_sqlite_memory_write": _base(
            "runtime_sqlite_memory_write",
            "Use runtime_sqlite_memory_write to write a tiny tagged macro runtime memory.",
            args={"text": "macro runtime payload test memory", "kind": "macro_runtime_test", "tag": f"seed-{seed}"},
        ),
        "runtime_sqlite_memory_cleanup": _base(
            "runtime_sqlite_memory_cleanup",
            "Use runtime_sqlite_memory_cleanup dry-run for macro_runtime_test tagged rows.",
            args={"kind": "macro_runtime_test", "tag": f"seed-{seed}", "apply": False},
        ),
        "vulkan_helper": _base(
            "vulkan_helper",
            "Use vulkan_helper as internal composite helper to summarize the configured lab repo briefly.",
            args={"task": "summarize the configured lab repo briefly", "reason": "macro runtime composite helper coverage"},
            max_steps=10,
        ),
    }


def missing_cases_for_tools(tool_names: set[str], cases: dict[str, ToolCase]) -> list[str]:
    return sorted(tool_names - set(cases))
