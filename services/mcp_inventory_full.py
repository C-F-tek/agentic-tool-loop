#!/usr/bin/env python3
"""
Complete MCP Server Inventory
Generated: 2026-08-04

This file contains the full inventory of all MCP servers and their tools.
"""

# =============================================================================
# MCP SERVER INVENTORY
# =============================================================================

MCP_SERVERS = {
    "aicarmine-codex-app": {
        "file": "services/codex_bridge/mcp_server.py",
        "tools": [
            {"name": "aicarmine_bridge_health", "description": "Local MCP health. No HTTP call and no agentic loop."},
            {"name": "terminal_list_files", "description": "Direct terminal-style file listing through in-process dispatcher. Read-only."},
            {"name": "terminal_search_files", "description": "Direct terminal-style file search through in-process dispatcher. Read-only."},
            {"name": "planner_scratchpad_write", "description": "Write planner scratchpad memory through direct dispatcher. No agentic loop."},
            {"name": "runtime_sqlite_memory_write", "description": "Write runtime SQLite memory through direct dispatcher. No agentic loop."},
            {"name": "aicarmine_repo_capabilities", "description": "Direct repo capability map through in-process dispatcher. Read-only."},
            {"name": "aicarmine_repo_status", "description": "Direct git/repository status through in-process dispatcher. Read-only."},
            {"name": "aicarmine_repo_tree", "description": "Direct bounded repository tree listing. Read-only."},
            {"name": "aicarmine_repo_list_files", "description": "Direct file listing under a repo path. Read-only."},
            {"name": "aicarmine_repo_search", "description": "Direct broker-managed repository search. Read-only."},
            {"name": "aicarmine_repo_rg_search", "description": "Direct ripgrep-style repository search wrapper. Read-only."},
            {"name": "aicarmine_repo_fd_files", "description": "Direct fd-style file discovery wrapper. Read-only."},
            {"name": "aicarmine_repo_read", "description": "Direct read of one or more repo-relative files. Read-only."},
            {"name": "aicarmine_repo_ast_grep_search", "description": "Direct ast-grep search where available. Read-only."},
            {"name": "aicarmine_repo_ast_grep_dry_run", "description": "Direct ast-grep dry-run. Read-only."},
            {"name": "aicarmine_repo_tree_sitter_parse", "description": "Direct tree-sitter parse helper where available. Read-only."},
            {"name": "aicarmine_repo_ctags_symbols", "description": "Direct ctags symbol extraction where available. Read-only."},
            {"name": "aicarmine_repo_jq_query", "description": "Direct jq query helper for JSON files. Read-only."},
            {"name": "aicarmine_repo_propose_code_edit", "description": "Report-only code edit proposal helper. Does not write files."},
            {"name": "aicarmine_repo_unidiff_validate", "description": "Validate a unified diff without applying it."},
            {"name": "aicarmine_repo_git_apply_check", "description": "Run git-apply style patch check through the repo tool wrapper."},
            {"name": "aicarmine_repo_apply_patch", "description": "Apply exact old_text/new_text patch. Only exposed write tool."},
            {"name": "aicarmine_repo_validate", "description": "Run broker-defined validation. No free-form command input."},
            {"name": "aicarmine_repo_ruff_check", "description": "Run repo ruff check wrapper."},
            {"name": "aicarmine_repo_pyright_check", "description": "Run repo pyright check wrapper."},
            {"name": "aicarmine_repo_pytest_run", "description": "Run repo pytest wrapper with bounded args from the tool implementation."},
            {"name": "aicarmine_repo_shellcheck", "description": "Run shellcheck wrapper where available."},
            {"name": "aicarmine_repo_semgrep_scan", "description": "Run semgrep scan wrapper where available."},
            {"name": "aicarmine_jobs_status", "description": "Read local agent-job artifacts from filesystem. No HTTP call."},
            {"name": "aicarmine_job_detail", "description": "Read a local agent-job artifact directory by id. No HTTP call."},
            {"name": "aicarmine_memory_report", "description": "Read operational/persistent memory SQLite records. Read-only."},
            {"name": "aicarmine_memory_state_packet", "description": "Build compact context packet from read-only local memory records."},
        ],
        "tool_count": 32,
    },
    "aicarmine-repo-state": {
        "file": "services/codex_bridge/repo_state_mcp_server.py",
        "tools": [
            {"name": "aicarmine_repo_state_health", "description": "Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees."},
            {"name": "aicarmine_repo_state_status", "description": "Run deterministic read-only repo_status against the configured repo root."},
            {"name": "aicarmine_repo_state_capabilities", "description": "Run deterministic read-only repo_capabilities against the configured repo root."},
        ],
        "tool_count": 3,
    },
    "aicarmine-repo-search-det": {
        "file": "services/codex_bridge/repo_search_det_mcp_server.py",
        "tools": [
            {"name": "aicarmine_repo_search_det_health", "description": "Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees."},
            {"name": "aicarmine_repo_search_fd", "description": "Find files with fd inside the configured repo root."},
            {"name": "aicarmine_repo_search_rg", "description": "Search file contents with ripgrep JSON output inside the configured repo root."},
            {"name": "aicarmine_repo_search_jq", "description": "Run jq against json_text or a repo JSON file."},
            {"name": "aicarmine_repo_search_ast_grep", "description": "Run ast-grep search inside the configured repo root."},
            {"name": "aicarmine_repo_search_ast_grep_dry_run", "description": "Run ast-grep rewrite dry-run without writing source files."},
            {"name": "aicarmine_repo_search_tree_sitter_parse", "description": "Parse a Python file with tree-sitter and return syntax anchors."},
            {"name": "aicarmine_repo_search_ctags", "description": "List symbols with universal-ctags JSON output."},
        ],
        "tool_count": 8,
    },
    "aicarmine-ollama": {
        "file": "services/codex_bridge/ollama_mcp_server.py",
        "tools": [
            {"name": "ollama_health", "description": "Check Ollama service health"},
            {"name": "ollama_list_models", "description": "List available models"},
            {"name": "ollama_show_model", "description": "Show model details"},
            {"name": "ollama_pull_model", "description": "Pull a model from registry"},
            {"name": "ollama_delete_model", "description": "Delete a model"},
            {"name": "ollama_chat", "description": "Chat with a model"},
            {"name": "ollama_generate", "description": "Generate text from a model"},
            {"name": "ollama_create_model", "description": "Create a new model"},
            {"name": "ollama_copy_model", "description": "Copy a model"},
            {"name": "ollama_ps", "description": "List running models"},
            {"name": "ollama_tags", "description": "List model tags"},
        ],
        "tool_count": 11,
    },
    "aicarmine-ovms-reranker": {
        "file": "services/codex_bridge/ovms_mcp_server.py",
        "tools": [
            {"name": "ovms_health", "description": "Check OVMS service health"},
            {"name": "ovms_start", "description": "Start OVMS service"},
            {"name": "ovms_stop", "description": "Stop OVMS service"},
            {"name": "ovms_restart", "description": "Restart OVMS service"},
            {"name": "ovms_rerank", "description": "Perform reranking using OVMS"},
            {"name": "ovms_list_models", "description": "List available models"},
            {"name": "ovms_get_config", "description": "Get OVMS configuration"},
            {"name": "ovms_set_config", "description": "Set OVMS configuration"},
        ],
        "tool_count": 8,
    },
    "aicarmine-repo-validate": {
        "file": "services/codex_bridge/repo_validate_mcp_server.py",
        "tools": [
            {"name": "aicarmine_repo_validate_health", "description": "Report Python executable, cwd, repo root, branch, commit, available tools, and no-loop guarantees."},
            {"name": "aicarmine_repo_validate_diffcheck", "description": "Run repo_validate default git diff --check validation."},
            {"name": "aicarmine_repo_validate_ruff", "description": "Run ruff check with JSON diagnostics."},
            {"name": "aicarmine_repo_validate_pyright", "description": "Run pyright with JSON diagnostics."},
            {"name": "aicarmine_repo_validate_pytest", "description": "Run pytest on selected paths only when explicitly requested by the user."},
            {"name": "aicarmine_repo_validate_shellcheck", "description": "Run shellcheck JSON diagnostics on selected files."},
            {"name": "aicarmine_repo_validate_semgrep", "description": "Run semgrep JSON diagnostics with a pattern or config."},
            {"name": "aicarmine_repo_validate_probe_profiles", "description": "List static read-only probe profiles and report optional Hypothesis availability. Does not execute arbitrary Python."},
            {"name": "aicarmine_repo_validate_probe_run", "description": "Run a reviewed read-only probe profile with deterministic cases, Hypothesis-generated cases, or both. No network calls or source writes are permitted by the profile."},
        ],
        "tool_count": 9,
    },
    "aicarmine-repo-code": {
        "file": "services/codex_bridge/repo_code_mcp_server.py",
        "tools": [
            {"name": "aicarmine_repo_code_health", "description": "Report repo-code incubator MCP health and no-loop guarantees."},
            {"name": "aicarmine_repo_code_propose_edit", "description": "Build a report-only code edit proposal. Prefer multi-file structured_edit edits; use unified_diff only when already valid. Does not write source files."},
            {"name": "aicarmine_repo_code_unidiff_validate", "description": "Validate unified diff structure without applying it."},
            {"name": "aicarmine_repo_code_git_apply_check", "description": "Run git apply --check on a unified diff without applying it."},
            {"name": "aicarmine_repo_code_apply_patch", "description": "Apply either an exact old_text/new_text patch or a validated unified diff/change-set in the incubator MCP. Requires allow_source_write=true."},
        ],
        "tool_count": 5,
    },
    "aicarmine-git-readonly": {
        "file": "services/codex_bridge/git_readonly_mcp_server.py",
        "tools": [
            {"name": "aicarmine_git_readonly_health", "description": "Report Git read-only MCP health and allowed diagnostic commands."},
            {"name": "aicarmine_git_readonly_log", "description": "Read recent commits with a fixed structured format."},
            {"name": "aicarmine_git_readonly_show", "description": "Read one commit with stat and optional patch."},
            {"name": "aicarmine_git_readonly_diff", "description": "Read a bounded git diff for worktree, staged, or revision range."},
            {"name": "aicarmine_git_readonly_blame", "description": "Read line blame for a repo file and bounded line range."},
            {"name": "aicarmine_git_readonly_branch_compare", "description": "Compare a local branch with a remote tracking ref without fetching."},
        ],
        "tool_count": 6,
    },
    "aicarmine-sqlite-readonly": {
        "file": "services/codex_bridge/sqlite_readonly_mcp_server.py",
        "tools": [
            {"name": "aicarmine_sqlite_readonly_health", "description": "Report SQLite read-only MCP health, aliases, allowlist and safety guarantees."},
            {"name": "aicarmine_sqlite_readonly_list_databases", "description": "List allowlisted SQLite databases under known repo state and job artifact roots."},
            {"name": "aicarmine_sqlite_readonly_schema", "description": "Read table/view schema from an allowlisted SQLite database."},
            {"name": "aicarmine_sqlite_readonly_query", "description": "Run one bounded SELECT/WITH query against an allowlisted SQLite database."},
        ],
        "tool_count": 4,
    },
    "aicarmine-job-artifact": {
        "file": "services/codex_bridge/job_artifact_mcp_server.py",
        "tools": [
            {"name": "aicarmine_job_artifact_health", "description": "Report job artifact MCP health and read-only filesystem roots."},
            {"name": "aicarmine_job_artifact_list_jobs", "description": "List persisted agent jobs from allowlisted local artifact roots."},
            {"name": "aicarmine_job_artifact_summary", "description": "Summarize one persisted agent job without calling broker HTTP."},
            {"name": "aicarmine_job_artifact_events", "description": "Read filtered/tail events from a job events.ndjson file."},
            {"name": "aicarmine_job_artifact_final", "description": "Read final.json and final.md for a persisted agent job."},
            {"name": "aicarmine_job_artifact_tool_results", "description": "List or read job tool-result artifacts from tool-results/."},
            {"name": "aicarmine_job_artifact_subturns", "description": "Read support-subturn events and tool-result artifacts from a persisted job without broker HTTP."},
            {"name": "aicarmine_job_artifact_planner_payload", "description": "Read a planner-prompts step payload for a persisted agent job."},
            {"name": "aicarmine_job_artifact_rejections", "description": "Extract planner/controller rejection events from a job event log."},
        ],
        "tool_count": 9,
    },
    "aicarmine-job-view": {
        "file": "services/codex_bridge/job_view_mcp_server.py",
        "tools": [
            {"name": "aicarmine_job_view_health", "description": "Report job-view MCP health, render sources and read-only local renderer guarantees."},
            {"name": "aicarmine_job_view_list_views", "description": "List available local job HTML views and section renderers."},
            {"name": "aicarmine_job_view_render", "description": "Render one existing agent job HTML view locally without broker HTTP."},
            {"name": "aicarmine_job_view_render_section", "description": "Render one existing lazy/section HTML fragment locally without broker HTTP."},
            {"name": "aicarmine_job_view_ia_payload", "description": "Read the IA live control view payload directly from local job files."},
            {"name": "aicarmine_job_view_outline", "description": "Render a job view and return an HTML outline instead of the full document."},
            {"name": "aicarmine_job_view_links", "description": "Render a job view and extract links and lazy section URLs."},
            {"name": "aicarmine_job_view_validate_html", "description": "Render a job view and run bounded structural/safety checks on the HTML."},
        ],
        "tool_count": 8,
    },
    "aicarmine-project-memory": {
        "file": "services/codex_bridge/project_memory_mcp_server.py",
        "tools": [
            {"name": "aicarmine_project_memory_health", "description": "Report project-local memory MCP health, DB path and write guardrails."},
            {"name": "aicarmine_project_memory_search", "description": "Search project-local persistent memory records. Read-only."},
            {"name": "aicarmine_project_memory_get", "description": "Read one project-local memory record by record_id or active scope/key identity."},
            {"name": "aicarmine_project_memory_upsert_verified", "description": "Write or re-verify one memory record only with explicit source evidence."},
            {"name": "aicarmine_project_memory_mark_stale", "description": "Mark a memory record stale with explicit evidence for the invalidation."},
            {"name": "aicarmine_project_memory_supersede", "description": "Supersede a memory record by inserting a new verified record and linking the old one."},
            {"name": "aicarmine_project_memory_audit_sources", "description": "Audit source references for project-local memory records. Read-only."},
        ],
        "tool_count": 7,
    },
    "aicarmine-local-subagent": {
        "file": "services/codex_bridge/local_subagent_mcp_server.py",
        "tools": [
            {"name": "aicarmine_local_subagent_health", "description": "Report local subagent facade health and dedicated agentic-loop root/port policy."},
            {"name": "aicarmine_local_subagent_capabilities", "description": "Describe the local subagent facade over the dedicated Codex agentic loop."},
            {"name": "aicarmine_local_subagent_run_readonly", "description": "Run one bounded read-only local subagent task through the dedicated Codex agentic loop."},
        ],
        "tool_count": 3,
    },
    "aicarmine-agentic-loop-client": {
        "file": "services/codex_bridge/agentic_loop_client_mcp_server.py",
        "tools": [
            {"name": "aicarmine_agentic_loop_health", "description": "Report explicit dedicated agentic-loop client health; broker probe is opt-in."},
            {"name": "aicarmine_agentic_loop_capabilities", "description": "Describe the explicit Codex-to-dedicated-broker client and confirmation contract."},
            {"name": "aicarmine_agentic_loop_ensure_reranker", "description": "Ensure the local OVMS/BGE reranker is ready on 127.0.0.1:3550; starts the repo-local provider script only with explicit confirmation and only when the configured port is free."},
            {"name": "aicarmine_agentic_loop_ensure_broker", "description": "Ensure a dedicated broker instance is running with AICARMINE_LAB_REPO equal to the Codex MCP repo root; starts it only with explicit confirmation when the port is free."},
            {"name": "aicarmine_agentic_loop_run", "description": "Start a canonical broker agentic-loop job on the dedicated Codex port and return a compact Codex-safe terminal summary when available."},
            {"name": "aicarmine_agentic_loop_status", "description": "Fetch compact status for a dedicated broker agentic-loop job through the canonical router."},
            {"name": "aicarmine_agentic_loop_result", "description": "Fetch compact terminal result for a dedicated broker agentic-loop job through the canonical router."},
        ],
        "tool_count": 7,
    },
    "aicarmine-codex-ops": {
        "file": "services/codex_bridge/ops_mcp_server.py",
        "tools": [
            {"name": "aicarmine_codex_ops_health", "description": "Report Codex ops MCP health and no-loop/no-HTTP guarantees."},
            {"name": "aicarmine_mcp_inventory_health", "description": "Report known local MCP servers available for inventory probing over stdio."},
            {"name": "aicarmine_mcp_inventory_list_targets", "description": "List the static allowlist of local MCP servers available for inventory probing."},
            {"name": "aicarmine_mcp_inventory_probe", "description": "Run read-only stdio initialize/list/optional-health inventory probes against local MCP servers."},
            {"name": "aicarmine_service_state_health", "description": "Report service-state read-only scope and defaults."},
            {"name": "aicarmine_service_state_ports", "description": "Read local listening sockets without calling HTTP health endpoints."},
            {"name": "aicarmine_service_state_processes", "description": "Read matching local process command lines with CIM/PowerShell."},
            {"name": "aicarmine_service_state_logs", "description": "Read tails of repo-local log files only."},
            {"name": "aicarmine_service_state_snapshot", "description": "Return one read-only snapshot of ports, process command lines and repo-local log tails."},
        ],
        "tool_count": 9,
    },
    "aicarmine-rag": {
        "file": "services/codex_bridge/rag_mcp_server.py",
        "tools": [
            {"name": "aicarmine_rag_context", "description": "Search the Codex RAG SQLite/FTS5 index and optionally rerank candidates with the local BGE reranker."},
            {"name": "aicarmine_rag_index_status", "description": "Inspect the Codex RAG index, DB metadata, Git/.gitignore candidate surface, and reranker readiness."},
            {"name": "aicarmine_rag_reindex", "description": "Update the Codex RAG SQLite index. Default mode is delta over Git candidates: tracked plus untracked files not excluded by .gitignore."},
        ],
        "tool_count": 3,
    },
    "aicarmine-rag-router": {
        "file": "knowledge-RAG-UNIFIED/mcp_rag_router_server.py",
        "tools": [
            {"name": "rag_router_list_dbs", "description": "List all available RAG databases with metadata"},
            {"name": "rag_router_list_cross_refs", "description": "List cross-references between RAG databases"},
            {"name": "rag_router_list_topics", "description": "List topic categories and their database mappings"},
            {"name": "rag_router_analyze_query", "description": "Analyze a query and return relevant topics and suggested databases with confidence scores"},
            {"name": "rag_router_consolidate_plan", "description": "Create a consolidated query plan across relevant databases"},
            {"name": "rag_router_get_relevant_dbs", "description": "Get all databases relevant to a specific topic"},
            {"name": "rag_router_get_knowledge_summary", "description": "Get a comprehensive summary of all knowledge bases, their topics, and capabilities"},
        ],
        "tool_count": 7,
    },
    "aicarmine-broker-planner": {
        "file": "services/codex_bridge/broker_planner_mcp_server.py",
        "tools": [
            {"name": "planner_state_inspect", "description": "Inspect planner state"},
            {"name": "planner_decision_history", "description": "Get decision history"},
            {"name": "planner_tool_selection", "description": "Inspect tool selection"},
            {"name": "planner_validator_diagnostics", "description": "Get validator diagnostics"},
            {"name": "planner_evidence_contract", "description": "Inspect evidence contract"},
            {"name": "planner_loop_metrics", "description": "Get loop metrics"},
            {"name": "planner_list_jobs", "description": "List planner jobs"},
            {"name": "planner_config_summary", "description": "Get config summary"},
        ],
        "tool_count": 8,
    },
    "aicarmine-planner-components": {
        "file": "services/codex_bridge/planner_components_mcp_server.py",
        "tools": [
            {"name": "orientation_shadow", "description": "Test orientation shadow component - initial orientation evaluation"},
            {"name": "vulkan_repair", "description": "Test vulkan_repair component - planner decision repair"},
            {"name": "replan_specialist", "description": "Test replan_specialist component - replan specialist for validation rejection"},
            {"name": "guard_rejection", "description": "Test guard_rejection component - guard rejection signatures"},
            {"name": "incomprehensible_retry", "description": "Test incomprehensible_retry component - retry for incomprehensible planner output"},
        ],
        "tool_count": 5,
    },
}

# =============================================================================
# SUMMARY
# =============================================================================

def print_inventory():
    total_tools = 0
    total_servers = len(MCP_SERVERS)
    
    print("=" * 70)
    print("MCP SERVER INVENTORY")
    print("=" * 70)
    print(f"{'Server':<35} {'Tools':>8}")
    print("-" * 70)
    
    for server_name, server_data in MCP_SERVERS.items():
        tool_count = server_data["tool_count"]
        total_tools += tool_count
        print(f"{server_name:<35} {tool_count:>8}")
    
    print("-" * 70)
    print(f"{'TOTAL':<35} {total_tools:>8}")
    print(f"\nTotal servers: {total_servers}")
    print(f"Total tools: {total_tools}")
    print("=" * 70)


def write_inventory_file():
    """Write the full inventory to a markdown file."""
    lines = [
        "# MCP Server Inventory",
        "",
        "Generated: 2026-08-04",
        "",
        "## Summary",
        "",
        f"- **Total Servers**: {len(MCP_SERVERS)}",
        f"- **Total Tools**: {sum(s['tool_count'] for s in MCP_SERVERS.values())}",
        "",
        "## Server Details",
        "",
    ]
    
    for server_name, server_data in MCP_SERVERS.items():
        lines.append(f"### {server_name}")
        lines.append(f"**File**: `{server_data['file']}`")
        lines.append(f"**Tools**: {server_data['tool_count']}")
        lines.append("")
        lines.append("| # | Tool Name | Description |")
        lines.append("|---|-----------|-------------|")
        for i, tool in enumerate(server_data["tools"], 1):
            lines.append(f"| {i} | {tool['name']} | {tool['description']} |")
        lines.append("")
    
    with open("services/mcp_inventory.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"\nInventory written to services/mcp_inventory.md")


if __name__ == "__main__":
    print_inventory()
    write_inventory_file()