# MCP Servers Complete Analysis

## Overview

This document provides a comprehensive analysis of all MCP servers in the agentic-tool-loop workspace, organized by category with their capabilities, ports, and usage patterns.

## 1. Core Infrastructure Servers

### aicarmine-codex-app
- **Script**: `services/codex_bridge/mcp_server.py`
- **Purpose**: Master facade with 37 tools covering repository operations, terminal commands, memory writes, and validation
- **Tools**: 37 tools including `terminal_list_files`, `terminal_search_files`, `aicarmine_repo_*`, `planner_scratchpad_write`, `runtime_sqlite_memory_write`, `aicarmine_memory_report`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-codex-ops
- **Script**: `services/codex_bridge/ops_mcp_server.py`
- **Purpose**: Operations and inventory management
- **Tools**: 9 tools including `aicarmine_codex_ops_health`, `aicarmine_mcp_inventory_*`, `aicarmine_service_state_*`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

## 2. Repository Operations Servers

### aicarmine-repo-state
- **Script**: `services/codex_bridge/repo_state_mcp_server.py`
- **Purpose**: Read-only repository state (branch, commit, status)
- **Tools**: 3 tools - `aicarmine_repo_state_health`, `aicarmine_repo_state_status`, `aicarmine_repo_state_capabilities`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-repo-search-det
- **Script**: `services/codex_bridge/repo_search_det_mcp_server.py`
- **Purpose**: Deterministic repository search with multiple backends
- **Tools**: 8 tools - `aicarmine_repo_search_fd`, `aicarmine_repo_search_rg`, `aicarmine_repo_search_jq`, `aicarmine_repo_search_ast_grep`, `aicarmine_repo_search_tree_sitter_parse`, `aicarmine_repo_search_ctags`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-repo-code
- **Script**: `services/codex_bridge/repo_code_mcp_server.py`
- **Purpose**: Code editing with structured_edit and unified_diff support
- **Tools**: 5 tools - `aicarmine_repo_code_propose_edit`, `aicarmine_repo_code_unidiff_validate`, `aicarmine_repo_code_git_apply_check`, `aicarmine_repo_code_apply_patch`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-repo-validate
- **Script**: `services/codex_bridge/repo_validate_mcp_server.py`
- **Purpose**: Repository validation with ruff, pyright, pytest, shellcheck, semgrep
- **Tools**: 9 tools - `aicarmine_repo_validate_diffcheck`, `aicarmine_repo_validate_ruff`, `aicarmine_repo_validate_pyright`, `aicarmine_repo_validate_pytest`, `aicarmine_repo_validate_shellcheck`, `aicarmine_repo_validate_semgrep`, `aicarmine_repo_validate_probe_profiles`, `aicarmine_repo_validate_probe_run`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-git-readonly
- **Script**: `services/codex_bridge/git_readonly_mcp_server.py`
- **Purpose**: Read-only Git operations (log, show, diff, blame)
- **Tools**: 6 tools - `aicarmine_git_readonly_log`, `aicarmine_git_readonly_show`, `aicarmine_git_readonly_diff`, `aicarmine_git_readonly_blame`, `aicarmine_git_readonly_branch_compare`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

## 3. Runtime & Job Management Servers

### aicarmine-job-artifact
- **Script**: `services/codex_bridge/job_artifact_mcp_server.py`
- **Purpose**: Read-only job artifact inspection from filesystem
- **Tools**: 9 tools - `aicarmine_job_artifact_list_jobs`, `aicarmine_job_artifact_summary`, `aicarmine_job_artifact_events`, `aicarmine_job_artifact_final`, `aicarmine_job_artifact_tool_results`, `aicarmine_job_artifact_subturns`, `aicarmine_job_artifact_planner_payload`, `aicarmine_job_artifact_rejections`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-job-view
- **Script**: `services/codex_bridge/job_view_mcp_server.py`
- **Purpose**: Local HTML view rendering for job artifacts
- **Tools**: 8 tools - `aicarmine_job_view_list_views`, `aicarmine_job_view_render`, `aicarmine_job_view_render_section`, `aicarmine_job_view_ia_payload`, `aicarmine_job_view_outline`, `aicarmine_job_view_links`, `aicarmine_job_view_validate_html`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-agentic-loop-client
- **Script**: `services/codex_bridge/agentic_loop_client_mcp_server.py`
- **Purpose**: Explicit Codex-to-dedicated-broker client for agentic loop runs
- **Tools**: 7 tools - `aicarmine_agentic_loop_health`, `aicarmine_agentic_loop_capabilities`, `aicarmine_agentic_loop_ensure_reranker`, `aicarmine_agentic_loop_ensure_broker`, `aicarmine_agentic_loop_run`, `aicarmine_agentic_loop_status`, `aicarmine_agentic_loop_result`
- **Status**: Active, autoApprove all tools
- **Port**: 3579 (vulkan/agent)

### aicarmine-local-subagent
- **Script**: `services/codex_bridge/local_subagent_mcp_server.py`
- **Purpose**: Local subagent facade for bounded read-only agentic tasks
- **Tools**: 3 tools - `aicarmine_local_subagent_health`, `aicarmine_local_subagent_capabilities`, `aicarmine_local_subagent_run_readonly`
- **Status**: Active, autoApprove all tools
- **Port**: 3579 (dedicated Codex port)

### aicarmine-broker-planner
- **Script**: `services/codex_bridge/broker_planner_mcp_server.py`
- **Purpose**: Planner state inspection and decision history
- **Tools**: 8 tools - `planner_state_inspect`, `planner_decision_history`, `planner_tool_selection`, `planner_validator_diagnostics`, `planner_evidence_contract`, `planner_loop_metrics`, `planner_list_jobs`, `planner_config_summary`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-planner-components
- **Script**: `services/codex_bridge/planner_components_mcp_server.py`
- **Purpose**: Planner orientation and repair components
- **Tools**: 5 tools - `orientation_shadow`, `vulkan_repair`, `replan_specialist`, `guard_rejection`, `incomprehensible_retry`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

## 4. Data & Memory Servers

### aicarmine-project-memory
- **Script**: `services/codex_bridge/project_memory_mcp_server.py`
- **Purpose**: Project-local persistent memory with SQLite backend
- **Tools**: 7 tools - `aicarmine_project_memory_health`, `aicarmine_project_memory_search`, `aicarmine_project_memory_get`, `aicarmine_project_memory_upsert_verified`, `aicarmine_project_memory_mark_stale`, `aicarmine_project_memory_supersede`, `aicarmine_project_memory_audit_sources`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-sqlite-readonly
- **Script**: `services/codex_bridge/sqlite_readonly_mcp_server.py`
- **Purpose**: Read-only SQLite queries against allowlisted databases
- **Tools**: 4 tools - `aicarmine_sqlite_readonly_health`, `aicarmine_sqlite_readonly_list_databases`, `aicarmine_sqlite_readonly_schema`, `aicarmine_sqlite_readonly_query`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-rag
- **Script**: `services/codex_bridge/rag_mcp_server.py`
- **Purpose**: RAG context search and index management
- **Tools**: 3 tools - `aicarmine_rag_context`, `aicarmine_rag_index_status`, `aicarmine_rag_reindex`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

### aicarmine-rag-router
- **Script**: `knowledge-RAG-UNIFIED/mcp_rag_router_server.py`
- **Purpose**: RAG cross-reference and query planning across multiple databases
- **Tools**: 7 tools - `rag_router_list_dbs`, `rag_router_list_cross_refs`, `rag_router_list_topics`, `rag_router_analyze_query`, `rag_router_consolidate_plan`, `rag_router_get_relevant_dbs`, `rag_router_get_knowledge_summary`
- **Status**: Active, autoApprove all tools
- **Port**: N/A (stdio)

## 5. Model & Inference Servers

### aicarmine-ollama
- **Script**: `services/codex_bridge/ollama_mcp_server.py`
- **Purpose**: Ollama model management and inference
- **Tools**: 13 tools - `ollama_health`, `ollama_list_models`, `ollama_show_model`, `ollama_pull_model`, `ollama_delete_model`, `ollama_chat`, `ollama_generate`, `ollama_create_model`, `ollama_copy_model`, `ollama_ps`, `ollama_tags`
- **Status**: Active, autoApprove all tools
- **Port**: 11434 (ollama serve)

### aicarmine-ovms-reranker
- **Script**: `services/codex_bridge/ovms_mcp_server.py`
- **Purpose**: OpenVINO Model Server reranker management
- **Tools**: 8 tools - `ovms_health`, `ovms_start`, `ovms_stop`, `ovms_restart`, `ovms_rerank`, `ovms_list_models`, `ovms_get_config`, `ovms_set_config`
- **Status**: Active, autoApprove all tools
- **Port**: 3550 (ovms rest_port)

## 6. Batch & Parallel Processing

### aicarmine-batch
- **Script**: `services/codex_bridge/batch_mcp_server.py`
- **Purpose**: Batch execution and health checks
- **Tools**: 2 tools - `batch_execute`, `health_check`
- **Status**: DISABLED
- **Port**: N/A (stdio)

## Summary Statistics

- **Total MCP Servers**: 16
- **Active Servers**: 15
- **Disabled Servers**: 1 (aicarmine-batch)
- **Total Tools**: 95
- **Total AutoApprove Entries**: 95

## Runtime Ports

| Port | Service | Process |
|------|---------|---------|
| 3550 | OVMS Reranker | ovms.exe |
| 3551 | OVMS Reranker (alt) | N/A |
| 3560 | OVMS Reranker (alt) | N/A |
| 3571 | Vulkan Bridge | python.exe (uvicorn) |
| 3572 | Vulkan Tool Broker | python.exe (uvicorn) |
| 3579 | Agentic Loop Client | python.exe (uvicorn) |
| 8080 | N/A | N/A |
| 8888 | N/A | N/A |
| 8889 | N/A | N/A |
| 11434 | Ollama | ollama.exe |
| 11435 | Ollama (alt) | N/A |

## Recommendations

1. **Enable aicarmine-batch**: Consider enabling the batch server if batch execution is needed.
2. **Monitor ports**: All critical ports are active and listening.
3. **Tool coverage**: 95 tools across 16 servers provide comprehensive coverage for repository operations, runtime management, and model inference.