#!/usr/bin/env python3
"""
AICarmine Symbol Quick Reference Generator.

Scans all MCP server Python files in services/codex_bridge/ and extracts
structured tool metadata, then generates a machine-readable symbol reference
that enables immediate symbol comprehension without thinking overhead.

Output: .docs/tool_symbol_reference.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICES_ROOT = Path(__file__).resolve().parents[1] / "services" / "codex_bridge"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".docs"
OUTPUT_FILE = OUTPUT_DIR / "tool_symbol_reference.json"

# Tool name to category mapping (authoritative)
TOOL_CATEGORIES: dict[str, str] = {
    # Repository operations
    "aicarmine_repo_capabilities": "repo/state",
    "aicarmine_repo_status": "repo/state",
    "aicarmine_repo_tree": "repo/listing",
    "aicarmine_repo_list_files": "repo/listing",
    "aicarmine_repo_search": "repo/search",
    "aicarmine_repo_rg_search": "repo/search",
    "aicarmine_repo_fd_files": "repo/search",
    "aicarmine_repo_read": "repo/read",
    "aicarmine_repo_propose_code_edit": "repo/edit",
    "aicarmine_repo_unidiff_validate": "repo/validate",
    "aicarmine_repo_git_apply_check": "repo/validate",
    "aicarmine_repo_apply_patch": "repo/write",
    "aicarmine_repo_validate": "repo/validate",
    "aicarmine_repo_ruff_check": "repo/validate",
    "aicarmine_repo_pyright_check": "repo/validate",
    "aicarmine_repo_pytest_run": "repo/validate",
    "aicarmine_repo_shellcheck": "repo/validate",
    "aicarmine_repo_semgrep_scan": "repo/validate",
    "aicarmine_repo_ast_grep_search": "repo/search",
    "aicarmine_repo_ast_grep_dry_run": "repo/search",
    "aicarmine_repo_tree_sitter_parse": "repo/parse",
    "aicarmine_repo_ctags_symbols": "repo/symbols",
    "aicarmine_repo_jq_query": "repo/query",
    # Git operations
    "aicarmine_git_readonly_health": "git/health",
    "aicarmine_git_readonly_log": "git/history",
    "aicarmine_git_readonly_show": "git/history",
    "aicarmine_git_readonly_diff": "git/diff",
    "aicarmine_git_readonly_blame": "git/blame",
    "aicarmine_git_readonly_branch_compare": "git/compare",
    # Job operations
    "aicarmine_jobs_status": "job/status",
    "aicarmine_job_detail": "job/detail",
    "aicarmine_job_artifact_health": "job/health",
    "aicarmine_job_artifact_list_jobs": "job/list",
    "aicarmine_job_artifact_summary": "job/detail",
    "aicarmine_job_artifact_events": "job/events",
    "aicarmine_job_artifact_final": "job/final",
    "aicarmine_job_artifact_tool_results": "job/tools",
    "aicarmine_job_artifact_subturns": "job/turns",
    "aicarmine_job_artifact_planner_payload": "job/planner",
    "aicarmine_job_artifact_rejections": "job/rejections",
    "aicarmine_job_view_health": "job/view",
    "aicarmine_job_view_list_views": "job/view",
    "aicarmine_job_view_render": "job/render",
    "aicarmine_job_view_render_section": "job/render",
    "aicarmine_job_view_ia_payload": "job/ia",
    "aicarmine_job_view_outline": "job/outline",
    "aicarmine_job_view_links": "job/links",
    "aicarmine_job_view_validate_html": "job/validate",
    # Memory operations
    "aicarmine_memory_report": "memory/search",
    "aicarmine_memory_state_packet": "memory/packet",
    "aicarmine_project_memory_health": "memory/health",
    "aicarmine_project_memory_search": "memory/search",
    "aicarmine_project_memory_get": "memory/get",
    "aicarmine_project_memory_upsert_verified": "memory/write",
    "aicarmine_project_memory_mark_stale": "memory/stale",
    "aicarmine_project_memory_supersede": "memory/supersede",
    "aicarmine_project_memory_audit_sources": "memory/audit",
    # Search/AST operations
    "aicarmine_repo_search_fd": "search/fd",
    "aicarmine_repo_search_rg": "search/rg",
    "aicarmine_repo_search_jq": "search/jq",
    "aicarmine_repo_search_ast_grep": "search/astgrep",
    "aicarmine_repo_search_ast_grep_dry_run": "search/astgrep",
    "aicarmine_repo_search_tree_sitter_parse": "search/treesitter",
    "aicarmine_repo_search_ctags": "search/ctags",
    # RAG operations
    "aicarmine_rag_context": "rag/query",
    "aicarmine_rag_index_status": "rag/status",
    "aicarmine_rag_reindex": "rag/reindex",
    # Validation operations
    "aicarmine_repo_validate_health": "validate/health",
    "aicarmine_repo_validate_diffcheck": "validate/diff",
    "aicarmine_repo_validate_ruff": "validate/ruff",
    "aicarmine_repo_validate_pyright": "validate/pyright",
    "aicarmine_repo_validate_pytest": "validate/pytest",
    "aicarmine_repo_validate_shellcheck": "validate/shellcheck",
    "aicarmine_repo_validate_semgrep": "validate/semgrep",
    "aicarmine_repo_validate_probe_profiles": "validate/probe",
    "aicarmine_repo_validate_probe_run": "validate/probe",
    # Agentic loop operations
    "aicarmine_agentic_loop_health": "agentic/health",
    "aicarmine_agentic_loop_capabilities": "agentic/capabilities",
    "aicarmine_agentic_loop_ensure_reranker": "agentic/ensure",
    "aicarmine_agentic_loop_ensure_broker": "agentic/ensure",
    "aicarmine_agentic_loop_run": "agentic/run",
    "aicarmine_agentic_loop_status": "agentic/status",
    "aicarmine_agentic_loop_result": "agentic/result",
    # Local subagent operations
    "aicarmine_local_subagent_health": "subagent/health",
    "aicarmine_local_subagent_capabilities": "subagent/capabilities",
    "aicarmine_local_subagent_run_readonly": "subagent/run",
    # Repo code operations
    "aicarmine_repo_code_health": "code/health",
    "aicarmine_repo_code_propose_edit": "code/propose",
    "aicarmine_repo_code_unidiff_validate": "code/validate",
    "aicarmine_repo_code_git_apply_check": "code/apply_check",
    "aicarmine_repo_code_apply_patch": "code/apply",
    # Ops operations
    "aicarmine_codex_ops_health": "ops/health",
    "aicarmine_mcp_inventory_health": "ops/inventory",
    "aicarmine_mcp_inventory_list_targets": "ops/inventory",
    "aicarmine_mcp_inventory_probe": "ops/probe",
    "aicarmine_service_state_health": "ops/state",
    "aicarmine_service_state_ports": "ops/ports",
    "aicarmine_service_state_processes": "ops/processes",
    "aicarmine_service_state_logs": "ops/logs",
    "aicarmine_service_state_snapshot": "ops/snapshot",
    # State operations
    "aicarmine_repo_state_health": "state/health",
    "aicarmine_repo_state_status": "state/status",
    "aicarmine_repo_state_capabilities": "state/capabilities",
    # SQLite operations
    "aicarmine_sqlite_readonly_health": "sqlite/health",
    "aicarmine_sqlite_readonly_list_databases": "sqlite/list",
    "aicarmine_sqlite_readonly_schema": "sqlite/schema",
    "aicarmine_sqlite_readonly_query": "sqlite/query",
    # Bridge/legacy operations
    "aicarmine_bridge_health": "bridge/health",
    "aicarmine_repo_search": "repo/search",
    "aicarmine_repo_status": "repo/state",
    "aicarmine_repo_tree": "repo/listing",
    "aicarmine_repo_read": "repo/read",
    "aicarmine_jobs_status": "job/status",
    "aicarmine_job_detail": "job/detail",
    "aicarmine_memory_report": "memory/search",
    "aicarmine_memory_state_packet": "memory/packet",
    # Terminal operations
    "terminal_list_files": "terminal/list",
    "terminal_search_files": "terminal/search",
    # Planner operations
    "planner_scratchpad_write": "planner/write",
    # Runtime operations
    "runtime_sqlite_memory_write": "runtime/write",
    # Wily operations (code complexity metrics)
    "wily_health": "wily/health",
    "wily_list_files": "wily/listing",
    "wily_complexity": "wily/complexity",
    "wily_maintainability": "wily/maintainability",
    "wily_report": "wily/report",
}

# Tool descriptions (authoritative, from MCP contract)
TOOL_DESCRIPTIONS: dict[str, str] = {
    # Repository operations
    "aicarmine_repo_capabilities": "List repository capability map (read-only)",
    "aicarmine_repo_status": "Get repository status: branch, commit, dirty state (read-only)",
    "aicarmine_repo_tree": "List directory tree with bounded depth and file count",
    "aicarmine_repo_list_files": "List files under a path with optional glob filter",
    "aicarmine_repo_search": "Broker-managed repository search (generic)",
    "aicarmine_repo_rg_search": "Direct ripgrep-style file content search",
    "aicarmine_repo_fd_files": "Direct fd-style file discovery by pattern",
    "aicarmine_repo_read": "Read one or more file contents with character limit",
    "aicarmine_repo_propose_code_edit": "Report-only code edit proposal (does not write)",
    "aicarmine_repo_unidiff_validate": "Validate unified diff structure without applying",
    "aicarmine_repo_git_apply_check": "Run git-apply --check without applying",
    "aicarmine_repo_apply_patch": "Apply exact old_text/new_text patch (write tool)",
    "aicarmine_repo_validate": "Run broker-defined validation suite",
    "aicarmine_repo_ruff_check": "Run ruff linter check",
    "aicarmine_repo_pyright_check": "Run pyright type checker",
    "aicarmine_repo_pytest_run": "Run pytest test suite",
    "aicarmine_repo_shellcheck": "Run shellcheck on shell scripts",
    "aicarmine_repo_semgrep_scan": "Run semgrep security scan",
    "aicarmine_repo_ast_grep_search": "Run ast-grep semantic search",
    "aicarmine_repo_ast_grep_dry_run": "Run ast-grep rewrite dry-run (no write)",
    "aicarmine_repo_tree_sitter_parse": "Parse file with tree-sitter for AST",
    "aicarmine_repo_ctags_symbols": "Extract symbols with universal-ctags",
    "aicarmine_repo_jq_query": "Run jq query against JSON file",
    # Git operations
    "aicarmine_git_readonly_health": "Report Git MCP health",
    "aicarmine_git_readonly_log": "Read recent commits with structured format",
    "aicarmine_git_readonly_show": "Read one commit with stat and optional patch",
    "aicarmine_git_readonly_diff": "Read bounded git diff for worktree or revisions",
    "aicarmine_git_readonly_blame": "Read line-by-line blame for a file",
    "aicarmine_git_readonly_branch_compare": "Compare branch with remote tracking",
    # Job operations
    "aicarmine_jobs_status": "Read agent-job artifacts from filesystem",
    "aicarmine_job_detail": "Read a job artifact directory by ID",
    "aicarmine_job_artifact_health": "Report job artifact MCP health",
    "aicarmine_job_artifact_list_jobs": "List persisted agent jobs",
    "aicarmine_job_artifact_summary": "Summarize one job without HTTP call",
    "aicarmine_job_artifact_events": "Read filtered/tail events from job",
    "aicarmine_job_artifact_final": "Read final.json and final.md for a job",
    "aicarmine_job_artifact_tool_results": "List or read tool-result artifacts",
    "aicarmine_job_artifact_subturns": "Read support-subturn events and results",
    "aicarmine_job_artifact_planner_payload": "Read planner step payload",
    "aicarmine_job_artifact_rejections": "Extract planner rejection events",
    "aicarmine_job_view_health": "Report job-view MCP health",
    "aicarmine_job_view_list_views": "List available job HTML views",
    "aicarmine_job_view_render": "Render one job HTML view locally",
    "aicarmine_job_view_render_section": "Render one section HTML fragment",
    "aicarmine_job_view_ia_payload": "Read IA live control payload directly",
    "aicarmine_job_view_outline": "Render view and return HTML outline",
    "aicarmine_job_view_links": "Render view and extract links",
    "aicarmine_job_view_validate_html": "Render view and run structural checks",
    # Memory operations
    "aicarmine_memory_report": "Search operational/persistent memory records",
    "aicarmine_memory_state_packet": "Build compact context packet from memory",
    "aicarmine_project_memory_health": "Report project-local memory health",
    "aicarmine_project_memory_search": "Search project-local memory records",
    "aicarmine_project_memory_get": "Read one memory record by ID or key",
    "aicarmine_project_memory_upsert_verified": "Write/verify memory record (write)",
    "aicarmine_project_memory_mark_stale": "Mark memory record stale",
    "aicarmine_project_memory_supersede": "Supersede memory record",
    "aicarmine_project_memory_audit_sources": "Audit source references",
    # Search operations
    "aicarmine_repo_search_fd": "Find files with fd in repo root",
    "aicarmine_repo_search_rg": "Search contents with ripgrep JSON output",
    "aicarmine_repo_search_jq": "Run jq against JSON text or file",
    "aicarmine_repo_search_ast_grep": "Run ast-grep search in repo",
    "aicarmine_repo_search_ast_grep_dry_run": "Run ast-grep rewrite dry-run",
    "aicarmine_repo_search_tree_sitter_parse": "Parse file with tree-sitter",
    "aicarmine_repo_search_ctags": "List symbols with ctags JSON output",
    # RAG operations
    "aicarmine_rag_context": "Search RAG SQLite index and optionally rerank",
    "aicarmine_rag_index_status": "Inspect RAG index, DB metadata, reranker",
    "aicarmine_rag_reindex": "Update RAG SQLite index (delta or full)",
    # Validation operations
    "aicarmine_repo_validate_health": "Report repo-validate MCP health",
    "aicarmine_repo_validate_diffcheck": "Run git diff --check validation",
    "aicarmine_repo_validate_ruff": "Run ruff check with JSON diagnostics",
    "aicarmine_repo_validate_pyright": "Run pyright with JSON diagnostics",
    "aicarmine_repo_validate_pytest": "Run pytest on selected paths",
    "aicarmine_repo_validate_shellcheck": "Run shellcheck JSON diagnostics",
    "aicarmine_repo_validate_semgrep": "Run semgrep JSON diagnostics",
    "aicarmine_repo_validate_probe_profiles": "List static probe profiles",
    "aicarmine_repo_validate_probe_run": "Run reviewed probe profile",
    # Agentic loop operations
    "aicarmine_agentic_loop_health": "Report agentic-loop client health",
    "aicarmine_agentic_loop_capabilities": "Describe agentic-loop client contract",
    "aicarmine_agentic_loop_ensure_reranker": "Ensure BGE reranker is ready",
    "aicarmine_agentic_loop_ensure_broker": "Ensure dedicated broker is running",
    "aicarmine_agentic_loop_run": "Start agentic-loop job on dedicated port",
    "aicarmine_agentic_loop_status": "Fetch compact status for a job",
    "aicarmine_agentic_loop_result": "Fetch compact result for a job",
    # Local subagent operations
    "aicarmine_local_subagent_health": "Report local subagent facade health",
    "aicarmine_local_subagent_capabilities": "Describe local subagent capabilities",
    "aicarmine_local_subagent_run_readonly": "Run bounded read-only subagent task",
    # Repo code operations
    "aicarmine_repo_code_health": "Report repo-code MCP health",
    "aicarmine_repo_code_propose_edit": "Build report-only code edit proposal",
    "aicarmine_repo_code_unidiff_validate": "Validate unified diff structure",
    "aicarmine_repo_code_git_apply_check": "Run git apply --check",
    "aicarmine_repo_code_apply_patch": "Apply verified patch (write tool)",
    # Ops operations
    "aicarmine_codex_ops_health": "Report Codex ops MCP health",
    "aicarmine_mcp_inventory_health": "Report MCP inventory health",
    "aicarmine_mcp_inventory_list_targets": "List allowlist of MCP servers",
    "aicarmine_mcp_inventory_probe": "Run stdio initialize/health probes",
    "aicarmine_service_state_health": "Report service-state read-only scope",
    "aicarmine_service_state_ports": "Read listening sockets",
    "aicarmine_service_state_processes": "Read process command lines",
    "aicarmine_service_state_logs": "Read tails of log files",
    "aicarmine_service_state_snapshot": "Return bounded snapshot of ports/processes/logs",
    # State operations
    "aicarmine_repo_state_health": "Report repo state health",
    "aicarmine_repo_state_status": "Run deterministic repo status",
    "aicarmine_repo_state_capabilities": "Run deterministic repo capabilities",
    # SQLite operations
    "aicarmine_sqlite_readonly_health": "Report SQLite read-only MCP health",
    "aicarmine_sqlite_readonly_list_databases": "List allowlisted SQLite databases",
    "aicarmine_sqlite_readonly_schema": "Read table/view schema",
    "aicarmine_sqlite_readonly_query": "Run bounded SELECT/WITH query",
    # Bridge/legacy operations
    "aicarmine_bridge_health": "Report bridge health (no HTTP call)",
    "terminal_list_files": "Direct terminal-style file listing",
    "terminal_search_files": "Direct terminal-style file search",
    "planner_scratchpad_write": "Write planner scratchpad memory",
    "runtime_sqlite_memory_write": "Write runtime SQLite memory",
    "wily_health": "Report Wily MCP health and Python analysis availability",
    "wily_list_files": "List Python files in a directory for complexity analysis",
    "wily_complexity": "Compute cyclomatic complexity for a Python file",
    "wily_maintainability": "Compute maintainability index for a Python file",
    "wily_report": "Generate full complexity and maintainability report",
}

# Write gates: tools that require explicit confirmation
WRITE_GATED_TOOLS: set[str] = {
    "aicarmine_repo_apply_patch",
    "aicarmine_project_memory_upsert_verified",
    "aicarmine_project_memory_mark_stale",
    "aicarmine_project_memory_supersede",
    "aicarmine_repo_code_apply_patch",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_write",
    "aicarmine_agentic_loop_run",
    "aicarmine_agentic_loop_ensure_broker",
    "aicarmine_agentic_loop_ensure_reranker",
}

# Confirmation gate argument mapping
CONFIRMATION_GATES: dict[str, str] = {
    "aicarmine_repo_apply_patch": "allow_source_write",
    "aicarmine_project_memory_upsert_verified": "confirm_write",
    "aicarmine_project_memory_mark_stale": "confirm_stale",
    "aicarmine_project_memory_supersede": "confirm_supersede",
    "aicarmine_repo_code_apply_patch": "allow_source_write",
    "aicarmine_agentic_loop_run": "confirm_agentic_loop",
    "aicarmine_agentic_loop_status": "confirm_agentic_loop",
    "aicarmine_agentic_loop_result": "confirm_agentic_loop",
    "aicarmine_agentic_loop_ensure_broker": "confirm_ensure_broker",
    "aicarmine_agentic_loop_ensure_reranker": "confirm_ensure_reranker",
}


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_tool_names_from_file(file_path: Path) -> list[str]:
    """Extract tool names from a Python MCP server file."""
    content = file_path.read_text(encoding="utf-8")
    tools: list[str] = []

    # Pattern 1: ToolSpec registration (authoritative)
    # matches: tools["tool_name"] = ToolSpec(name="tool_name", ...)
    toolspec_pattern = r'tools\["([^"]*(?:aicarmine|terminal|planner|runtime|wily)[^"]*)"\]\s*=\s*ToolSpec\('
    for match in re.finditer(toolspec_pattern, content):
        tools.append(match.group(1))

    # Pattern 2: Docstring list of tools (e.g., "  - aicarmine_repo_read")
    docstring_pattern = r'-\s+(aicarmine_\w+|terminal_\w+|wily_\w+)'
    for match in re.finditer(docstring_pattern, content):
        tools.append(match.group(1))

    # Pattern 3: TOOL_NAMES = [...] or TOOL_NAMES = {...}
    pattern_list = r'TOOL_NAMES\s*=\s*\[([^\]]+)\]'
    for match in re.finditer(pattern_list, content):
        bracket_content = match.group(1)
        for item in re.findall(r'["\']([^"\']+)["\']', bracket_content):
            tools.append(item)

    # Pattern 4: JSON schema tool name definitions
    json_pattern = r'"name"\s*:\s*"([^"]*(?:aicarmine|terminal|wily)[^"]*)"'
    for match in re.finditer(json_pattern, content):
        tools.append(match.group(1))

    # Pattern 5: Function definitions that look like tool handlers
    pattern_define = r'def\s+((?:handle_|tool_)?(?:aicarmine_\w+|terminal_\w+|wily_\w+))'
    for match in re.finditer(pattern_define, content):
        tools.append(match.group(1))

    return list(dict.fromkeys(tools))  # dedupe while preserving order


def _extract_server_name(file_path: Path) -> str:
    """Extract MCP server name from file path."""
    stem = file_path.stem
    # Map file names to server names
    name_map = {
        "mcp_server": "aicarmine-codex-app",
        "repo_state_mcp_server": "aicarmine-repo-state",
        "repo_search_det_mcp_server": "aicarmine-repo-search-det",
        "rag_mcp_server": "aicarmine-rag",
        "repo_validate_mcp_server": "aicarmine-repo-validate",
        "git_readonly_mcp_server": "aicarmine-git-readonly",
        "sqlite_readonly_mcp_server": "aicarmine-sqlite-readonly",
        "job_artifact_mcp_server": "aicarmine-job-artifact",
        "job_view_mcp_server": "aicarmine-job-view",
        "project_memory_mcp_server": "aicarmine-project-memory",
        "local_subagent_mcp_server": "aicarmine-local-subagent",
        "agentic_loop_client_mcp_server": "aicarmine-agentic-loop-client",
        "repo_code_mcp_server": "aicarmine-repo-code",
        "ops_mcp_server": "aicarmine-codex-ops",
        "wily_mcp_server": "aicarmine-wily",
    }
    return name_map.get(stem, stem)


def _determine_read_only(tool_name: str) -> bool:
    """Determine if a tool is read-only based on write gate list."""
    return tool_name not in WRITE_GATED_TOOLS


def _get_confirmation_gate(tool_name: str) -> str | None:
    """Get the confirmation gate argument for a tool."""
    return CONFIRMATION_GATES.get(tool_name)


# ---------------------------------------------------------------------------
# Reference generation
# ---------------------------------------------------------------------------

def generate_tool_entry(tool_name: str, server_name: str, category: str) -> dict[str, Any]:
    """Generate a structured entry for one tool."""
    description = TOOL_DESCRIPTIONS.get(tool_name, f"MCP tool: {tool_name}")
    is_read_only = _determine_read_only(tool_name)
    confirmation_gate = _get_confirmation_gate(tool_name)

    # Determine category sub-types
    category_parts = category.split("/")
    family = category_parts[0] if category_parts else "unknown"
    subtype = category_parts[1] if len(category_parts) > 1 else "general"

    # Determine related tools (same category)
    related = [
        t for t, cat in TOOL_CATEGORIES.items()
        if cat == category and t != tool_name
    ][:5]  # Limit to 5 related tools

    entry: dict[str, Any] = {
        "tool_name": tool_name,
        "server_name": server_name,
        "category": category,
        "family": family,
        "subtype": subtype,
        "description": description,
        "read_only": is_read_only,
        "confirmation_gate": confirmation_gate,
        "related_tools": related,
    }

    # Add required confirmation value if gated
    if confirmation_gate:
        entry["confirmation_required"] = True
        entry["confirmation_value"] = tool_name  # Tool name is the confirmation value
    else:
        entry["confirmation_required"] = False

    return entry


def generate_symbol_reference() -> dict[str, Any]:
    """Generate the complete symbol reference."""
    tools_by_server: dict[str, list[str]] = {}
    tools_by_category: dict[str, list[str]] = {}

    # Scan all MCP server files
    if not SERVICES_ROOT.exists():
        print(f"Warning: services root not found at {SERVICES_ROOT}", file=sys.stderr)
        return {}

    for py_file in sorted(SERVICES_ROOT.glob("*.py")):
        if py_file.stem.startswith("__"):
            continue

        server_name = _extract_server_name(py_file)
        tool_names = _extract_tool_names_from_file(py_file)

        if tool_names:
            tools_by_server[server_name] = tool_names

            for tool_name in tool_names:
                category = TOOL_CATEGORIES.get(tool_name, "unknown/general")
                if category not in tools_by_category:
                    tools_by_category[category] = []
                tools_by_category[category].append(tool_name)

    # Build tool entries
    tool_entries: list[dict[str, Any]] = []
    for server_name, tool_names in sorted(tools_by_server.items()):
        for tool_name in sorted(tool_names):
            category = TOOL_CATEGORIES.get(tool_name, "unknown/general")
            entry = generate_tool_entry(tool_name, server_name, category)
            tool_entries.append(entry)

    # Build category index
    category_index: dict[str, list[str]] = {}
    for category, tools in sorted(tools_by_category.items()):
        category_index[category] = sorted(tools)

    # Build family summary
    family_summary: dict[str, dict[str, Any]] = {}
    for entry in tool_entries:
        family = entry["family"]
        if family not in family_summary:
            family_summary[family] = {
                "tool_count": 0,
                "read_only_count": 0,
                "write_count": 0,
                "categories": [],
            }
        family_summary[family]["tool_count"] += 1
        if entry["read_only"]:
            family_summary[family]["read_only_count"] += 1
        else:
            family_summary[family]["write_count"] += 1
        if entry["category"] not in family_summary[family]["categories"]:
            family_summary[family]["categories"].append(entry["category"])

    reference = {
        "schema": "aicarmine_tool_symbol_reference.v1",
        "version": "1.0.0",
        "generated_at": "runtime",
        "metadata": {
            "total_tools": len(tool_entries),
            "total_servers": len(tools_by_server),
            "total_categories": len(tools_by_category),
            "write_gated_tools": len(WRITE_GATED_TOOLS),
        },
        "tool_entries": tool_entries,
        "category_index": category_index,
        "family_summary": family_summary,
        "write_gated_tools": sorted(WRITE_GATED_TOOLS),
        "confirmation_gates": {
            k: v for k, v in sorted(CONFIRMATION_GATES.items())
        },
    }

    return reference


def main() -> None:
    """Generate and write the symbol reference."""
    reference = generate_symbol_reference()

    if not reference:
        print("Error: failed to generate reference", file=sys.stderr)
        sys.exit(1)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write output
    OUTPUT_FILE.write_text(
        json.dumps(reference, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Symbol reference written to: {OUTPUT_FILE}")
    print(f"Total tools: {reference['metadata']['total_tools']}")
    print(f"Total servers: {reference['metadata']['total_servers']}")
    print(f"Total categories: {reference['metadata']['total_categories']}")


if __name__ == "__main__":
    main()