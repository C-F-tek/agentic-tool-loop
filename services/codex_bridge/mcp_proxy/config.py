"""
AICarmine MCP Proxy - Configuration

Defines target servers, script paths, routing map, and environment settings.
"""

import os
from pathlib import Path

# Base directory for this package
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# Target Servers
# =============================================================================
TARGET_SERVERS = [
    "aicarmine-codex-app",
    "aicarmine-repo-state",
    "aicarmine-repo-search-det",
    "aicarmine-repo-code",
    "aicarmine-repo-validate",
    "aicarmine-git-readonly",
    "aicarmine-sqlite-readonly",
    "aicarmine-job-artifact",
    "aicarmine-job-view",
    "aicarmine-project-memory",
    "aicarmine-local-subagent",
    "aicarmine-agentic-loop-client",
    "aicarmine-codex-ops",
    "aicarmine-ollama",
    "aicarmine-ovms-reranker",
    "aicarmine-rag-router",
    "aicarmine-broker-planner",
    "aicarmine-planner-components",
    "aicarmine-planner-scratchpad",
    "aicarmine-runtime-sqlite-memory",
    "aicarmine-evidence-builder",
]

# =============================================================================
# Server Script Paths (relative to workspace root)
# =============================================================================
SERVER_SCRIPTS = {
    "aicarmine-codex-app": "services/codex_bridge/mcp_server.py",
    "aicarmine-repo-state": "services/codex_bridge/repo_state_mcp_server.py",
    "aicarmine-repo-search-det": "services/codex_bridge/repo_search_det_mcp_server.py",
    "aicarmine-repo-code": "services/codex_bridge/repo_code_mcp_server.py",
    "aicarmine-repo-validate": "services/codex_bridge/repo_validate_mcp_server.py",
    "aicarmine-git-readonly": "services/codex_bridge/git_readonly_mcp_server.py",
    "aicarmine-sqlite-readonly": "services/codex_bridge/sqlite_readonly_mcp_server.py",
    "aicarmine-job-artifact": "services/codex_bridge/job_artifact_mcp_server.py",
    "aicarmine-job-view": "services/codex_bridge/job_view_mcp_server.py",
    "aicarmine-project-memory": "services/codex_bridge/project_memory_mcp_server.py",
    "aicarmine-local-subagent": "services/codex_bridge/local_subagent_mcp_server.py",
    "aicarmine-agentic-loop-client": "services/codex_bridge/agentic_loop_client_mcp_server.py",
    "aicarmine-codex-ops": "services/codex_bridge/ops_mcp_server.py",
    "aicarmine-ollama": "services/codex_bridge/ollama_mcp_server.py",
    "aicarmine-ovms-reranker": "services/codex_bridge/ovms_mcp_server.py",
    "aicarmine-rag-router": "knowledge-RAG-UNIFIED/mcp_rag_router_server.py",
    "aicarmine-broker-planner": "services/codex_bridge/broker_planner_mcp_server.py",
    "aicarmine-planner-components": "services/codex_bridge/planner_components_mcp_server.py",
    "aicarmine-planner-scratchpad": "services/codex_bridge/planner_scratchpad_mcp_server.py",
    "aicarmine-runtime-sqlite-memory": "services/codex_bridge/runtime_sqlite_memory_mcp_server.py",
    "aicarmine-evidence-builder": "services/codex_bridge/evidence_builder_mcp_server.py",
}

# =============================================================================
# Route Map: tool_name_pattern -> server_name
# =============================================================================
ROUTE_MAP = {
    # aicarmine-codex-app tools
    "repo_status": "aicarmine-codex-app",
    "repo_capabilities": "aicarmine-codex-app",
    "repo_tree": "aicarmine-codex-app",
    "list_files": "aicarmine-codex-app",
    "search_files": "aicarmine-codex-app",
    "repo_read": "aicarmine-codex-app",
    "repo_propose_code_edit": "aicarmine-codex-app",
    "unidiff_validate": "aicarmine-codex-app",
    "git_apply_check": "aicarmine-codex-app",
    "apply_patch": "aicarmine-codex-app",
    "repo_validate": "aicarmine-codex-app",
    "ruff_check": "aicarmine-codex-app",
    "pyright_check": "aicarmine-codex-app",
    "pytest_run": "aicarmine-codex-app",
    "shellcheck": "aicarmine-codex-app",
    "semgrep_scan": "aicarmine-codex-app",
    "scratchpad_write": "aicarmine-codex-app",
    "scratchpad_read": "aicarmine-codex-app",
    "sqlite_memory_write": "aicarmine-codex-app",
    "sqlite_memory_read": "aicarmine-codex-app",

    # aicarmine-repo-state tools
    "repo_state_health": "aicarmine-repo-state",
    "repo_status": "aicarmine-repo-state",
    "repo_capabilities": "aicarmine-repo-state",

    # aicarmine-repo-search-det tools
    "search_fd": "aicarmine-repo-search-det",
    "search_rg": "aicarmine-repo-search-det",
    "search_ast_grep": "aicarmine-repo-search-det",
    "search_ast_grep_dry_run": "aicarmine-repo-search-det",
    "tree_sitter_parse": "aicarmine-repo-search-det",
    "ctags_symbols": "aicarmine-repo-search-det",
    "jq_query": "aicarmine-repo-search-det",

    # aicarmine-repo-code tools
    "propose_edit": "aicarmine-repo-code",
    "unidiff_validate": "aicarmine-repo-code",
    "git_apply_check": "aicarmine-repo-code",
    "apply_patch": "aicarmine-repo-code",
    "health": "aicarmine-repo-code",

    # aicarmine-repo-validate tools
    "diffcheck": "aicarmine-repo-validate",
    "ruff": "aicarmine-repo-validate",
    "pyright": "aicarmine-repo-validate",
    "pytest": "aicarmine-repo-validate",
    "shellcheck": "aicarmine-repo-validate",
    "semgrep": "aicarmine-repo-validate",
    "probe_profiles": "aicarmine-repo-validate",
    "probe_run": "aicarmine-repo-validate",

    # aicarmine-git-readonly tools
    "git_log": "aicarmine-git-readonly",
    "git_show": "aicarmine-git-readonly",
    "git_diff": "aicarmine-git-readonly",
    "git_blame": "aicarmine-git-readonly",
    "branch_compare": "aicarmine-git-readonly",

    # aicarmine-sqlite-readonly tools
    "list_databases": "aicarmine-sqlite-readonly",
    "schema": "aicarmine-sqlite-readonly",
    "query": "aicarmine-sqlite-readonly",

    # aicarmine-job-artifact tools
    "jobs_status": "aicarmine-job-artifact",
    "job_detail": "aicarmine-job-artifact",
    "job_events": "aicarmine-job-artifact",
    "job_final": "aicarmine-job-artifact",
    "tool_results": "aicarmine-job-artifact",
    "subturns": "aicarmine-job-artifact",
    "planner_payload": "aicarmine-job-artifact",
    "rejections": "aicarmine-job-artifact",

    # aicarmine-job-view tools
    "list_views": "aicarmine-job-view",
    "render": "aicarmine-job-view",
    "render_section": "aicarmine-job-view",
    "ia_payload": "aicarmine-job-view",
    "outline": "aicarmine-job-view",
    "links": "aicarmine-job-view",
    "validate_html": "aicarmine-job-view",

    # aicarmine-project-memory tools
    "memory_health": "aicarmine-project-memory",
    "memory_search": "aicarmine-project-memory",
    "memory_get": "aicarmine-project-memory",
    "memory_upsert_verified": "aicarmine-project-memory",
    "memory_mark_stale": "aicarmine-project-memory",
    "memory_supersede": "aicarmine-project-memory",
    "audit_sources": "aicarmine-project-memory",

    # aicarmine-agentic-loop-client tools (via codex-app)
    "loop_run": "aicarmine-agentic-loop-client",
    "loop_status": "aicarmine-agentic-loop-client",
    "loop_result": "aicarmine-agentic-loop-client",

    # aicarmine-codex-ops tools
    "ops_health": "aicarmine-codex-ops",
    "mcp_inventory_health": "aicarmine-codex-ops",
    "mcp_inventory_list_targets": "aicarmine-codex-ops",
    "mcp_inventory_probe": "aicarmine-codex-ops",
    "service_state_health": "aicarmine-codex-ops",
    "service_state_ports": "aicarmine-codex-ops",
    "service_state_processes": "aicarmine-codex-ops",
    "service_state_logs": "aicarmine-codex-ops",
    "service_state_snapshot": "aicarmine-codex-ops",

    # aicarmine-ollama tools
    "ollama_health": "aicarmine-ollama",
    "ollama_list_models": "aicarmine-ollama",
    "ollama_show_model": "aicarmine-ollama",
    "ollama_pull_model": "aicarmine-ollama",
    "ollama_delete_model": "aicarmine-ollama",
    "ollama_chat": "aicarmine-ollama",
    "ollama_generate": "aicarmine-ollama",
    "ollama_create_model": "aicarmine-ollama",
    "ollama_copy_model": "aicarmine-ollama",
    "ollama_ps": "aicarmine-ollama",
    "ollama_tags": "aicarmine-ollama",

    # aicarmine-ovms-reranker tools
    "ovms_health": "aicarmine-ovms-reranker",
    "ovms_start": "aicarmine-ovms-reranker",
    "ovms_stop": "aicarmine-ovms-reranker",
    "ovms_restart": "aicarmine-ovms-reranker",
    "ovms_rerank": "aicarmine-ovms-reranker",
    "ovms_list_models": "aicarmine-ovms-reranker",
    "ovms_get_config": "aicarmine-ovms-reranker",
    "ovms_set_config": "aicarmine-ovms-reranker",

    # aicarmine-rag-router tools
    "rag_router_list_dbs": "aicarmine-rag-router",
    "rag_router_list_cross_refs": "aicarmine-rag-router",
    "rag_router_list_topics": "aicarmine-rag-router",
    "rag_router_analyze_query": "aicarmine-rag-router",
    "rag_router_consolidate_plan": "aicarmine-rag-router",
    "rag_router_get_relevant_dbs": "aicarmine-rag-router",
    "rag_router_get_knowledge_summary": "aicarmine-rag-router",

    # aicarmine-broker-planner tools
    "planner_state_inspect": "aicarmine-broker-planner",
    "planner_decision_history": "aicarmine-broker-planner",
    "planner_tool_selection": "aicarmine-broker-planner",
    "planner_validator_diagnostics": "aicarmine-broker-planner",
    "planner_evidence_contract": "aicarmine-broker-planner",
    "planner_loop_metrics": "aicarmine-broker-planner",
    "planner_list_jobs": "aicarmine-broker-planner",
    "planner_config_summary": "aicarmine-broker-planner",

    # aicarmine-planner-components tools
    "orientation_shadow": "aicarmine-planner-components",
    "vulkan_repair": "aicarmine-planner-components",
    "replan_specialist": "aicarmine-planner-components",
    "guard_rejection": "aicarmine-planner-components",
    "incomprehensible_retry": "aicarmine-planner-components",

    # aicarmine-planner-scratchpad tools
    "scratchpad_read": "aicarmine-planner-scratchpad",
    "scratchpad_write": "aicarmine-planner-scratchpad",
    "scratchpad_search": "aicarmine-planner-scratchpad",
    "scratchpad_delete": "aicarmine-planner-scratchpad",

    # aicarmine-runtime-sqlite-memory tools
    "runtime_sqlite_memory_read": "aicarmine-runtime-sqlite-memory",
    "runtime_sqlite_memory_write": "aicarmine-runtime-sqlite-memory",
    "runtime_sqlite_memory_search": "aicarmine-runtime-sqlite-memory",

    # aicarmine-evidence-builder tools
    "evidence_builder_build": "aicarmine-evidence-builder",
    "evidence_builder_search": "aicarmine-evidence-builder",

    # aicarmine-local-subagent tools
    "subagent_run_readonly": "aicarmine-local-subagent",

    # aicarmine-rag tools (if added)
    "rag_context": "aicarmine-rag",
    "rag_index_status": "aicarmine-rag",
    "rag_reindex": "aicarmine-rag",

    # Default fallback
    "default": "aicarmine-codex-app",
}

# =============================================================================
# Environment defaults for proxy server launch
# =============================================================================
PYTHON_EXECUTABLE = r"C:\Users\sanit\AppData\Local\Programs\Python\Python312\python.exe"

DEFAULT_ENV = {
    "AICARMINE_CODEX_MCP_REPO_ROOT": ".",
    "AICARMINE_LAB_REPO": ".",
    "AICARMINE_MCP_GZIP_ENABLED": "1",
    "AICARMINE_MCP_GZIP_THRESHOLD": "8192",
    "PATH": r"C:\Users\sanit\AppData\Local\Programs\Python\Python314;C:\Users\sanit\AppData\Local\Programs\Python\Python314\Scripts;%PATH%",
}
# Dopo DEFAULT_ENV, aggiungi:
DEFAULT_SERVER = "aicarmine-agentic-loop"
# =============================================================================
# Proxy Server Settings
# =============================================================================
PROXY_SERVER_NAME = "aicarmine-proxy"
PROXY_DESCRIPTION = "AICarmine MCP Proxy - Unified gateway for all MCP servers"

# Rate limiting default
DEFAULT_MAX_CALLS_PER_MINUTE = 30

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"