"""Canonical tool registry for the 3571/3572 broker contract.

This module is deliberately pure data plus small pure helpers. It does not
dispatch tools, read request payloads, call HTTP, or touch job state.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

REGISTRY_VERSION = "2026-06-01.registry-v2"
RUNTIME_CONTRACT = (
    "3571 receives OpenWebUI tool call -> 3571 forwards to 3572 and waits -> "
    "3572 runs the agentic planner loop -> 3572 wraps the terminal result -> "
    "3572 returns wrapper to 3571 -> 3571 returns ok/result wrapper to OpenWebUI"
)


def _tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    argument_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
    }
    if required:
        parameters["required"] = required
    if isinstance(argument_contract, dict):
        requires_one_of = argument_contract.get("requires_one_of")
        if isinstance(requires_one_of, list) and requires_one_of:
            parameters["anyOf"] = [
                {"required": [str(field) for field in group if str(field).strip()]}
                for group in requires_one_of
                if isinstance(group, list) and any(str(field).strip() for field in group)
            ]
    function: dict[str, Any] = {"name": name, "description": description, "parameters": parameters}
    if isinstance(argument_contract, dict) and argument_contract:
        function["argument_contract"] = argument_contract
    return {"type": "function", "function": function}


_SCHEMAS: dict[str, dict[str, Any]] = {
    "repo_capabilities": _tool_schema(
        "repo_capabilities",
        "Return available local repo/file tools, public/internal surfaces, required arguments, examples and safety policy.",
    ),
    "repo_status": _tool_schema(
        "repo_status",
        "Read real git status, diff stat, changed files, diff check and stack.",
    ),
    "repo_tree": _tool_schema(
        "repo_tree",
        "List repo-relative files and directories under a path. Use for directory structure, module layout, file inventory or key files.",
        {
            "path": {"type": "string", "default": "."},
            "max_depth": {"type": "integer", "default": 3},
            "max_files": {"type": "integer", "default": 200},
        },
        argument_contract={"default_allowed": {"path": ".", "max_depth": 3, "max_files": 200}},
    ),
    "repo_list_files": _tool_schema(
        "repo_list_files",
        "List repo-relative files by path, suffix and limit. Prefer over repo_search for glob-like requests.",
        {
            "path": {"type": "string", "default": "."},
            "suffix": {"type": "string", "default": ""},
            "extension": {"type": "string", "default": ""},
            "limit": {"type": "integer", "default": 20},
            "max_files": {"type": "integer", "default": 20},
            "max_depth": {"type": "integer", "default": 50},
            "core": {"type": "boolean", "default": False},
            "exclude_dirs": {"type": "array", "items": {"type": "string"}},
        },
        argument_contract={"default_allowed": {"path": ".", "suffix": "", "limit": 20}},
    ),
    "repo_search": _tool_schema(
        "repo_search",
        "Search repo code/docs by query/pattern/symbol. Requires query, pattern or symbol.",
        {
            "query": {"type": "string"},
            "pattern": {"type": "string"},
            "symbol": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "mode": {"type": "string", "enum": ["rg", "git_grep", "fd"], "default": "rg"},
            "max_results": {"type": "integer", "default": 80},
        },
        argument_contract={
            "requires_one_of": [["query"], ["pattern"], ["symbol"]],
            "violation": "repo_search_missing_query_pattern_or_symbol",
        },
    ),
    "repo_semantic_search": _tool_schema(
        "repo_semantic_search",
        (
            "Semantic repo search over the delta RAG index. Use before targeted repo_read "
            "when lexical search or repo_tree is too broad. Requires query."
        ),
        {
            "query": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "limit": {"type": "integer", "default": 8},
            "top_k": {"type": "integer", "default": 8},
            "max_results": {"type": "integer", "default": 8},
            "candidate_limit": {"type": "integer", "default": 64},
            "max_chunk_chars": {"type": "integer", "default": 1200},
            "reindex": {"type": "boolean", "default": True},
            "rerank": {"type": "boolean", "default": True},
            "rerank_candidate_limit": {"type": "integer", "default": 12},
            "rerank_doc_chars": {"type": "integer", "default": 2500},
            "rerank_timeout_seconds": {"type": "number", "default": 30.0},
        },
        ["query"],
        argument_contract={"required": ["query"]},
    ),
    "repo_fd_files": _tool_schema(
        "repo_fd_files",
        "Deterministic fd file discovery. Use for fast repo file lists before targeted reads.",
        {
            "pattern": {"type": "string"},
            "query": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "extension": {"type": "string"},
            "suffix": {"type": "string"},
            "limit": {"type": "integer", "default": 200},
            "max_results": {"type": "integer", "default": 200},
            "timeout_seconds": {"type": "integer", "default": 60},
        },
        argument_contract={"default_allowed": {"path": ".", "pattern": "", "limit": 200}},
    ),
    "repo_rg_search": _tool_schema(
        "repo_rg_search",
        "Deterministic ripgrep search with structured match payload.",
        {
            "pattern": {"type": "string"},
            "query": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "max_results": {"type": "integer", "default": 80},
            "limit": {"type": "integer", "default": 80},
            "context": {"type": "integer", "default": 0},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={"requires_one_of": [["pattern"], ["query"]], "violation": "repo_rg_search_missing_pattern"},
    ),
    "repo_jq_query": _tool_schema(
        "repo_jq_query",
        "Run jq over inline JSON or a repo-relative JSON file and return parsed output.",
        {
            "query": {"type": "string"},
            "filter": {"type": "string"},
            "json_text": {"type": "string"},
            "path": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 60},
        },
        argument_contract={"requires_one_of": [["query"], ["filter"]], "violation": "repo_jq_query_missing_query"},
    ),
    "repo_ast_grep_search": _tool_schema(
        "repo_ast_grep_search",
        "AST structural search with ast-grep. Evidence/dry-run only; no source writes.",
        {
            "pattern": {"type": "string"},
            "kind": {"type": "string"},
            "rewrite": {"type": "string"},
            "lang": {"type": "string", "default": "python"},
            "language": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={"requires_one_of": [["pattern"], ["kind"]], "violation": "repo_ast_grep_search_missing_pattern_or_kind"},
    ),
    "repo_ast_grep_dry_run": _tool_schema(
        "repo_ast_grep_dry_run",
        "AST rewrite dry-run with ast-grep. Returns matches/rewrite evidence; does not apply.",
        {
            "pattern": {"type": "string"},
            "rewrite": {"type": "string"},
            "lang": {"type": "string", "default": "python"},
            "language": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={
            "required": ["pattern", "rewrite"],
            "source_writes_performed": False,
            "patch_application_performed": False,
        },
    ),
    "repo_tree_sitter_parse": _tool_schema(
        "repo_tree_sitter_parse",
        "Parse a repo-relative Python file with Tree-sitter and return structural anchors.",
        {
            "path": {"type": "string"},
            "language": {"type": "string", "default": "python"},
            "lang": {"type": "string"},
        },
        ["path"],
        argument_contract={"required": ["path"], "violation": "repo_tree_sitter_parse_missing_path"},
    ),
    "repo_unidiff_validate": _tool_schema(
        "repo_unidiff_validate",
        "Parse and validate a complete unified diff with python-unidiff.",
        {
            "unified_diff": {"type": "string"},
            "diff": {"type": "string"},
        },
        argument_contract={"requires_one_of": [["unified_diff"], ["diff"]], "violation": "repo_unidiff_validate_missing_diff"},
    ),
    "repo_git_apply_check": _tool_schema(
        "repo_git_apply_check",
        "Validate a unified diff with git apply --check without applying it.",
        {
            "unified_diff": {"type": "string"},
            "diff": {"type": "string"},
            "patch": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={"requires_one_of": [["unified_diff"], ["diff"], ["patch"]], "patch_application_performed": False},
    ),
    "repo_ruff_check": _tool_schema(
        "repo_ruff_check",
        "Run ruff check on repo-relative Python paths and return JSON diagnostics.",
        {
            "path": {"type": "string", "default": "."},
            "paths": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "default": 180},
        },
        argument_contract={"default_allowed": {"path": "."}},
    ),
    "repo_pyright_check": _tool_schema(
        "repo_pyright_check",
        "Run pyright type checking on repo-relative paths and return JSON output.",
        {
            "path": {"type": "string", "default": "."},
            "paths": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "default": 240},
        },
        argument_contract={"default_allowed": {"path": "."}},
    ),
    "repo_pytest_run": _tool_schema(
        "repo_pytest_run",
        "Run targeted pytest validation on repo-relative paths.",
        {
            "path": {"type": "string", "default": "."},
            "paths": {"type": "array", "items": {"type": "string"}},
            "marker": {"type": "string"},
            "maxfail": {"type": "integer", "default": 1},
            "timeout_seconds": {"type": "integer", "default": 300},
        },
        argument_contract={"default_allowed": {"path": ".", "maxfail": 1}},
    ),
    "repo_shellcheck": _tool_schema(
        "repo_shellcheck",
        "Run ShellCheck on repo-relative shell script files and return JSON comments.",
        {
            "path": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={"requires_one_of": [["path"], ["paths"]], "violation": "repo_shellcheck_missing_path"},
    ),
    "repo_ctags_symbols": _tool_schema(
        "repo_ctags_symbols",
        "Generate a bounded Universal Ctags symbol map for repo-relative paths.",
        {
            "path": {"type": "string", "default": "."},
            "paths": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 500},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        argument_contract={"default_allowed": {"path": ".", "limit": 500}},
    ),
    "repo_semgrep_scan": _tool_schema(
        "repo_semgrep_scan",
        "Run Semgrep local pattern/config scan and return JSON findings.",
        {
            "pattern": {"type": "string"},
            "config": {"type": "string"},
            "lang": {"type": "string", "default": "python"},
            "language": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "paths": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "default": 240},
        },
        argument_contract={"requires_one_of": [["pattern"], ["config"]], "violation": "repo_semgrep_scan_missing_pattern_or_config"},
    ),
    "repo_hyperfine_benchmark": _tool_schema(
        "repo_hyperfine_benchmark",
        "Run explicit-consent hyperfine benchmarks for validation/performance work.",
        {
            "commands": {"type": "array", "items": {"type": "string"}},
            "runs": {"type": "integer", "default": 3},
            "warmup": {"type": "integer", "default": 1},
            "timeout_seconds": {"type": "integer", "default": 600},
            "user_consent": {"type": "string"},
        },
        ["commands"],
        argument_contract={"required": ["commands"], "requires_explicit_consent": True},
    ),
    "repo_read": _tool_schema(
        "repo_read",
        "Read one or more repo-relative files. Requires path, paths, item or items.",
        {
            "path": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
            "item": {"type": "object"},
            "items": {"type": "array", "items": {"type": "object"}},
            "max_chars": {"type": "integer", "default": 80000},
            "line": {"type": "integer"},
            "before": {"type": "integer", "default": 40},
            "after": {"type": "integer", "default": 120},
        },
        argument_contract={
            "requires_one_of": [["path"], ["paths"], ["item"], ["items"]],
            "violation": "repo_read_missing_path_or_paths_items",
        },
    ),
    "repo_propose_code_edit": _tool_schema(
        "repo_propose_code_edit",
        (
            "Produce a complete report-only code edit proposal for diff/refactoring goals. "
            "Does not write source files or apply patches. Requires full unified_diff, structured_operations, "
            "or explicit no_op rationale. For exact replacements after repo_read, prefer old_text/new_text "
            "and let the tool generate the full unified diff."
        ),
        {
            "target_file": {"type": "string"},
            "path": {"type": "string"},
            "edit_kind": {"type": "string", "enum": ["unified_diff", "structured_edit", "no_op"]},
            "rationale": {"type": "string"},
            "unified_diff": {"type": "string"},
            "structured_operations": {"type": "array", "items": {"type": "object"}},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "validation_commands": {"type": "array", "items": {"type": "string"}},
            "require_unidiff": {"type": "boolean", "default": True},
            "ast_anchor": {"type": "string"},
            "ast_grep_rule": {"type": "string"},
            "tree_sitter_language": {"type": "string", "enum": ["python"]},
        },
        ["target_file", "edit_kind", "rationale"],
        argument_contract={
            "required": ["target_file", "edit_kind", "rationale"],
            "conditional_required": [
                {
                    "when": {"edit_kind": "unified_diff"},
                    "requires_one_of": [["unified_diff"], ["old_text", "new_text"]],
                    "violation": "repo_propose_code_edit_missing_unified_diff",
                },
                {
                    "when": {"edit_kind": "structured_edit"},
                    "requires": ["structured_operations"],
                    "violation": "repo_propose_code_edit_missing_structured_operations",
                },
                {
                    "when": {"edit_kind": "no_op"},
                    "forbidden_any": ["unified_diff", "structured_operations", "old_text", "new_text"],
                    "violation": "repo_propose_code_edit_no_op_has_patch_payload",
                },
            ],
            "note": "repo_propose_code_edit is report-only; it does not infer a diff from a generic rationale.",
            "source_requirements": {
                "old_text": "Must be exact text from verified repo_read target content or explicit user exact old_text that was then verified against the target.",
                "new_text": "May be new content; it does not need to already exist in the file.",
                "sqlite_windows": "If target content is windowed, read real planner_scratchpad_read windows from required_working_set/candidate_next_actions before proposing.",
            },
            "shape_examples": [
                {
                    "example_only": True,
                    "not_runnable": True,
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": "EXAMPLE_ONLY/path.py",
                        "edit_kind": "unified_diff",
                        "rationale": "EXAMPLE_ONLY_DO_NOT_COPY: exact replacement from verified repo_read content.",
                        "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                        "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                    },
                }
            ],
        },
    ),
    "repo_apply_patch": _tool_schema(
        "repo_apply_patch",
        "Modify one repo-relative file by replacing exact old_text with new_text. Use only when exact old_text is known.",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "max_replacements": {"type": "integer", "default": 1},
        },
        ["path", "old_text", "new_text"],
        argument_contract={
            "required": ["path", "old_text", "new_text"],
            "source_requirements": {
                "old_text": "Must be exact text from verified repo_read target content; example text is invalid.",
                "new_text": "May be new content.",
            },
            "shape_examples": [
                {
                    "example_only": True,
                    "not_runnable": True,
                    "tool": "repo_apply_patch",
                    "arguments": {
                        "path": "EXAMPLE_ONLY/path.py",
                        "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                        "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                    },
                }
            ],
        },
    ),
    "repo_write_file": _tool_schema(
        "repo_write_file",
        "Create, overwrite or append a small repo-relative text file in LAB_REPO.",
        {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "mode": {"type": "string", "enum": ["overwrite", "create", "append"], "default": "overwrite"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        ["path", "content"],
        argument_contract={"required": ["path", "content"]},
    ),
    "repo_validate": _tool_schema(
        "repo_validate",
        "Run standard validation after changes: git diff --check and targeted Python compileall.",
        {
            "path": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
            "commands": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "default": 300},
            "continue_on_failure": {"type": "boolean", "default": False},
        },
        argument_contract={
            "default_allowed": {
                "path": "repo-relative validation target",
                "paths": "repo-relative validation targets",
                "commands": "standard validation",
                "timeout_seconds": 300,
            }
        },
    ),
    "repo_command": _tool_schema(
        "repo_command",
        "Run a safe diagnostic command. Requires command. Dangerous commands require explicit consent.",
        {
            "command": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 120},
            "user_consent": {"type": "string"},
        },
        ["command"],
        argument_contract={"required": ["command"], "violation": "repo_command_missing_command"},
    ),
    "terminal_list_files": _tool_schema(
        "terminal_list_files",
        "Internal Windows-aware file listing. Not exposed on the OpenWebUI public surface.",
        {
            "directory": {"type": "string"},
            "path": {"type": "string"},
            "pattern": {"type": "string", "default": "*"},
            "recurse": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 200},
        },
        argument_contract={"default_allowed": {"directory": "project terminal cwd", "pattern": "*", "limit": 200}},
    ),
    "terminal_search_files": _tool_schema(
        "terminal_search_files",
        "Internal Windows-aware filename/content search. Not exposed on the OpenWebUI public surface.",
        {
            "query": {"type": "string"},
            "directory": {"type": "string"},
            "path": {"type": "string"},
            "content": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 200},
        },
        ["query"],
        argument_contract={"required": ["query"], "violation": "terminal_search_files_missing_query"},
    ),
    "terminal_run_command_wait": _tool_schema(
        "terminal_run_command_wait",
        "Internal synchronous PowerShell diagnostic command. Not exposed on the OpenWebUI public surface.",
        {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
            "directory": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 120},
            "user_consent": {"type": "string"},
        },
        ["command"],
        argument_contract={"required": ["command"], "violation": "terminal_run_command_wait_missing_command"},
    ),
    "planner_scratchpad_write": _tool_schema(
        "planner_scratchpad_write",
        "Internal job-scoped scratchpad write. Not exposed on the OpenWebUI public surface.",
        {
            "text": {"type": "string"},
            "content": {"type": "string"},
            "kind": {"type": "string", "default": "note"},
            "tag": {"type": "string"},
        },
        argument_contract={
            "requires_one_of": [["text"], ["content"]],
            "violation": "planner_scratchpad_write_missing_text",
            "shape_examples": [
                {
                    "example_only": True,
                    "not_runnable": True,
                    "tool": "planner_scratchpad_write",
                    "arguments": {
                        "kind": "code_product_build_state",
                        "target_file": "EXAMPLE_ONLY/path.py",
                        "text": "{\"schema\":\"code_product_build_state.v1\",\"target_file\":\"EXAMPLE_ONLY/path.py\",\"status\":\"collecting_source\",\"source_windows\":[{\"document_id\":\"EXAMPLE_ONLY_DO_NOT_COPY_doc\",\"offset\":0,\"complete\":false,\"sha256\":\"EXAMPLE_ONLY_DO_NOT_COPY_hash\"}],\"rationale\":\"EXAMPLE_ONLY_DO_NOT_COPY real progress only\"}",
                    },
                }
            ],
        },
    ),
    "planner_scratchpad_read": _tool_schema(
        "planner_scratchpad_read",
        (
            "Internal job-scoped scratchpad read. Also reads SQLite-backed prompt_context_window "
            "documents by document_id/offset when planner prompt context was compacted. "
            "Not exposed on the OpenWebUI public surface."
        ),
        {
            "query": {"type": "string"},
            "tag": {"type": "string"},
            "kind": {"type": "string", "enum": ["note", "answer_chunk", "prompt_context", "prompt_context_window", "code_product_build_state"]},
            "document_id": {"type": "string"},
            "section": {"type": "string"},
            "offset": {"type": "integer", "default": 0},
            "max_chars": {"type": "integer", "default": 3000},
            "limit": {"type": "integer", "default": 50},
        },
        argument_contract={
            "requires_one_of": [["document_id"], ["section"], ["tag"], ["query"], ["kind"]],
            "violation": "planner_scratchpad_read_missing_selector",
            "note": "For prompt_context_window/code_product_build_state reads, prefer document_id+offset or section+offset.",
            "sqlite_window_contract": {
                "real_values_source": "Use document_id, section, offset, max_chars from required_working_set or candidate_next_actions only.",
                "has_more_after": "When true, the next read offset must be the window_end/next offset from evidence.",
                "duplicate_windows": "Repeating the same document_id/section/offset/max_chars is rejected.",
            },
            "shape_examples": [
                {
                    "example_only": True,
                    "not_runnable": True,
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": "prompt_context_window",
                        "document_id": "EXAMPLE_ONLY_DO_NOT_COPY_document_id",
                        "offset": 2500,
                        "max_chars": 2500,
                    },
                },
                {
                    "example_only": True,
                    "not_runnable": True,
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": "code_product_build_state",
                        "section": "EXAMPLE_ONLY_DO_NOT_COPY_section",
                        "offset": 0,
                        "max_chars": 8000,
                    },
                },
            ],
        },
    ),
    "runtime_sqlite_memory_search": _tool_schema(
        "runtime_sqlite_memory_search",
        "Internal broker-owned persistent SQLite/FTS5 planner memory search. Not exposed on OpenWebUI.",
        {
            "query": {"type": "string"},
            "kind": {"type": "string"},
            "tag": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
            "db": {"type": "string"},
        },
        argument_contract={
            "requires_one_of": [["query"], ["tag"], ["kind"]],
            "violation": "runtime_sqlite_memory_search_missing_query_tag_or_kind",
        },
    ),
    "runtime_sqlite_memory_write": _tool_schema(
        "runtime_sqlite_memory_write",
        "Internal broker-owned persistent SQLite/FTS5 planner memory write. Not exposed on OpenWebUI.",
        {
            "text": {"type": "string"},
            "content": {"type": "string"},
            "kind": {"type": "string", "default": "planner_note"},
            "tag": {"type": "string"},
            "metadata": {"type": "object"},
            "ttl_days": {"type": "integer"},
            "pinned": {"type": "boolean", "default": False},
            "db": {"type": "string"},
        },
        argument_contract={
            "requires_one_of": [["text"], ["content"]],
            "violation": "runtime_sqlite_memory_write_missing_text",
        },
    ),
    "runtime_sqlite_memory_cleanup": _tool_schema(
        "runtime_sqlite_memory_cleanup",
        "Internal broker-owned persistent memory cleanup. Defaults to dry-run; apply=true is required to delete.",
        {
            "dry_run": {"type": "boolean", "default": True},
            "apply": {"type": "boolean", "default": False},
            "kind": {"type": "string"},
            "tag": {"type": "string"},
            "older_than_days": {"type": "integer"},
            "expired_only": {"type": "boolean", "default": True},
            "pinned": {"type": "boolean", "default": False},
            "db": {"type": "string"},
        },
        argument_contract={"default_allowed": {"dry_run": True, "apply": False}},
    ),
    "vulkan_helper": _tool_schema(
        "vulkan_helper",
        "Internal composite helper for generic local repo/helper/multi-task requests.",
        {
            "public_tool_name": {"type": "string"},
            "task": {"type": "string"},
            "reason": {"type": "string"},
            "arguments": {"type": "object"},
        },
        ["public_tool_name", "task", "reason"],
        argument_contract={"required": ["public_tool_name", "task", "reason"]},
    ),
}
PLANNER_INTERNAL_TOOLS: tuple[str, ...] = (
    "repo_capabilities",
    "repo_status",
    "repo_tree",
    "repo_search",
    "repo_semantic_search",
    "repo_fd_files",
    "repo_rg_search",
    "repo_jq_query",
    "repo_ast_grep_search",
    "repo_ast_grep_dry_run",
    "repo_tree_sitter_parse",
    "repo_unidiff_validate",
    "repo_git_apply_check",
    "repo_ruff_check",
    "repo_pyright_check",
    "repo_pytest_run",
    "repo_shellcheck",
    "repo_ctags_symbols",
    "repo_semgrep_scan",
    "repo_hyperfine_benchmark",
    "repo_read",
    "repo_list_files",
    "repo_propose_code_edit",
    "repo_apply_patch",
    "repo_write_file",
    "repo_validate",
    "repo_command",
    "terminal_run_command_wait",
    "terminal_search_files",
    "terminal_list_files",
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
    "runtime_sqlite_memory_cleanup",
    "vulkan_helper",
)

OPENWEBUI_PUBLIC_TOOLS: tuple[str, ...] = (
    "helper_for_all",
    "help_for_all",
    "repo_capabilities",
    "repo_status",
    "repo_search",
    "repo_read",
    "repo_command",
    "vulkan_helper",
)

MCP_PUBLIC_TOOLS: tuple[str, ...] = (
    "aicarmine_bridge_health",
    "aicarmine_repo_capabilities",
    "aicarmine_repo_status",
    "aicarmine_repo_tree",
    "aicarmine_repo_list_files",
    "aicarmine_repo_search",
    "aicarmine_repo_read",
    "aicarmine_repo_apply_patch",
    "aicarmine_repo_write_file",
    "aicarmine_repo_validate",
    "aicarmine_repo_command",
    "aicarmine_vulkan_helper",
    "aicarmine_jobs_status",
    "aicarmine_job_detail",
    "aicarmine_memory_report",
    "aicarmine_memory_state_packet",
)

# Write-guarded tools: these change repo filesystem state (creates, overwrites,
# patches, or runs commands that may produce output files). Does not include
# scratchpad/memory/state writes (those are session-scoped, not repo-scoped).

WRITE_GUARDED_TOOLS: frozenset[str] = frozenset(
    {
        "repo_apply_patch",
        "repo_write_file",
        "repo_command",
        "terminal_run_command_wait",
        "repo_hyperfine_benchmark",
        "runtime_sqlite_memory_cleanup",
    }
)

READ_ONLY_TOOLS: frozenset[str] = frozenset(PLANNER_INTERNAL_TOOLS) - WRITE_GUARDED_TOOLS

TOOL_ALIASES: dict[str, str] = {
    "capabilities": "repo_capabilities",
    "tool_help": "repo_capabilities",
    "tools": "repo_capabilities",
    "help_tools": "repo_capabilities",
    "repo_help": "repo_capabilities",
    "status": "repo_status",
    "git_status": "repo_status",
    "get_git_status": "repo_status",
    "diff": "repo_status",
    "git_diff": "repo_status",
    "analyze_repo": "repo_status",
    "analyze_repository": "repo_status",
    "find_issues": "repo_status",
    "detect_problems": "repo_status",
    "search": "repo_search",
    "grep": "repo_search",
    "rg": "repo_search",
    "search_code": "repo_search",
    "semantic_search": "repo_semantic_search",
    "rag_search": "repo_semantic_search",
    "repo_rag_search": "repo_semantic_search",
    "fd": "repo_fd_files",
    "find_files_fd": "repo_fd_files",
    "ripgrep": "repo_rg_search",
    "rg_search": "repo_rg_search",
    "jq": "repo_jq_query",
    "json_query": "repo_jq_query",
    "ast_grep": "repo_ast_grep_search",
    "ast_search": "repo_ast_grep_search",
    "ast_grep_dry_run": "repo_ast_grep_dry_run",
    "tree_sitter_parse": "repo_tree_sitter_parse",
    "parse_ast": "repo_tree_sitter_parse",
    "unidiff_validate": "repo_unidiff_validate",
    "git_apply_check": "repo_git_apply_check",
    "ruff": "repo_ruff_check",
    "ruff_check": "repo_ruff_check",
    "pyright": "repo_pyright_check",
    "pyright_check": "repo_pyright_check",
    "pytest": "repo_pytest_run",
    "pytest_run": "repo_pytest_run",
    "shellcheck": "repo_shellcheck",
    "ctags": "repo_ctags_symbols",
    "symbols": "repo_ctags_symbols",
    "semgrep": "repo_semgrep_scan",
    "hyperfine": "repo_hyperfine_benchmark",
    "read": "repo_read",
    "read_file": "repo_read",
    "get_file_content": "repo_read",
    "propose_code_edit": "repo_propose_code_edit",
    "code_edit_proposal": "repo_propose_code_edit",
    "code_product": "repo_propose_code_edit",
    "patch_candidate": "repo_propose_code_edit",
    "diff_proposal": "repo_propose_code_edit",
    "apply_patch": "repo_apply_patch",
    "patch": "repo_apply_patch",
    "patch_file": "repo_apply_patch",
    "edit": "repo_apply_patch",
    "edit_file": "repo_apply_patch",
    "modify_file": "repo_apply_patch",
    "write_file": "repo_write_file",
    "create_file": "repo_write_file",
    "overwrite_file": "repo_write_file",
    "save_file": "repo_write_file",
    "validate": "repo_validate",
    "validation": "repo_validate",
    "smoke": "repo_validate",
    "command": "repo_command",
    "run": "repo_command",
    "compile": "repo_command",
    "terminal": "terminal_run_command_wait",
    "terminal_command": "terminal_run_command_wait",
    "run_command_wait": "terminal_run_command_wait",
    "powershell": "terminal_run_command_wait",
    "terminal_list_files": "terminal_list_files",
    "list_user_files": "terminal_list_files",
    "terminal_search_files": "terminal_search_files",
    "search_user_files": "terminal_search_files",
    "scratchpad_write": "planner_scratchpad_write",
    "scratchpad_read": "planner_scratchpad_read",
    "memory_search": "runtime_sqlite_memory_search",
    "memory_write": "runtime_sqlite_memory_write",
    "memory_cleanup": "runtime_sqlite_memory_cleanup",
    "runtime_sqlite_memory": "runtime_sqlite_memory_search",
    "tree": "repo_tree",
    "list_dir": "repo_tree",
    "directory": "repo_tree",
    "directory_structure": "repo_tree",
    "list_files": "repo_list_files",
    "file_inventory": "repo_list_files",
    "files": "repo_list_files",
    "find_files": "repo_list_files",
    "diff_check": "repo_command",
    "help": "vulkan_helper",
    "helper": "vulkan_helper",
    "helper_for_all": "vulkan_helper",
    "help_for_all": "vulkan_helper",
}

def tools_schema() -> list[dict[str, Any]]:
    return [copy.deepcopy(_SCHEMAS[name]) for name in PLANNER_INTERNAL_TOOLS]


TOOLS_SCHEMA: list[dict[str, Any]] = tools_schema()
TOOL_ARGUMENT_CONTRACTS: dict[str, dict[str, Any]] = {
    name: copy.deepcopy(schema.get("function", {}).get("argument_contract") or {})
    for name, schema in _SCHEMAS.items()
}
VALID_INTERNAL_TOOLS: frozenset[str] = frozenset(PLANNER_INTERNAL_TOOLS)
VALID_INTERNAL_TOOLS_LIST: list[str] = sorted(VALID_INTERNAL_TOOLS)
VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN: list[str] = [
    name for name in VALID_INTERNAL_TOOLS_LIST if name != "vulkan_helper"
]
VALID_INTERNAL_TOOLS_PROMPT: str = "|".join(VALID_INTERNAL_TOOLS_LIST)
VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN: str = "|".join(
    VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN
)
HELPER_PUBLIC_ALIASES: frozenset[str] = frozenset({"helper_for_all", "help_for_all", "helper", "help"})


def registry_hash() -> str:
    payload = {
        "version": REGISTRY_VERSION,
        "planner_internal": PLANNER_INTERNAL_TOOLS,
        "openwebui_public": OPENWEBUI_PUBLIC_TOOLS,
        "mcp_public": MCP_PUBLIC_TOOLS,
        "write_guarded": sorted(WRITE_GUARDED_TOOLS),
        "aliases": TOOL_ALIASES,
        "schemas": TOOLS_SCHEMA,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capability_map() -> dict[str, Any]:
    return {
        "registry_version": REGISTRY_VERSION,
        "registry_hash": registry_hash(),
        "runtime_contract": RUNTIME_CONTRACT,
        "surfaces": {
            "openwebui_public": list(OPENWEBUI_PUBLIC_TOOLS),
            "planner_internal": list(PLANNER_INTERNAL_TOOLS),
            "mcp_public": list(MCP_PUBLIC_TOOLS),
            "write_guarded": sorted(WRITE_GUARDED_TOOLS),
            "read_only": sorted(READ_ONLY_TOOLS),
        },
        "surface_policy": {
            "3571": "OpenWebUI public surface; forwards to 3572 and waits for the wrapped terminal result.",
            "3572": "Agentic planner loop; validates, repairs structured failures, executes internal tools.",
            "memory_tools_public_on_openwebui": False,
            "scratchpad_tools_public_on_openwebui": False,
            "terminal_tools_public_on_openwebui": False,
        },
        "module": __name__,
        "schema_tools": [item["function"]["name"] for item in TOOLS_SCHEMA],
    }
