# MCP Hook Improvements - All 16 Servers

## Overview

This document describes the improvements applied to all 16 MCP servers to enhance hook integration, health monitoring, fallback logging, performance metrics, security audit trail, configuration validation, auto-discovery, and error recovery.

## Improvements Applied

### 1. Health Check Integration

Each MCP server now includes:
- Automatic health checks before tool calls
- Cached health results to avoid repeated checks
- Stale MCP server status reporting

### 2. Fallback Logging

Each MCP server now includes:
- Logging when native tools are used instead of MCP
- Tracking of MCP failure patterns
- Generation of recommendations based on failure history

### 3. Performance Metrics

Each MCP server now includes:
- Tool call latency tracking by MCP server
- Identification of slow MCP servers for optimization
- Reporting of performance trends over time

### 4. Security Audit Trail

Each MCP server now includes:
- Logging of all MCP tool calls with timestamps
- Tracking of MCP server access patterns
- Generation of security reports for audit compliance

### 5. Configuration Validation

Each MCP server now includes:
- Validation of MCP server configurations before use
- Checking for outdated MCP server versions
- Reporting of deprecated tool usage

### 6. Auto-Discovery

Each MCP server now includes:
- Automatic discovery of new MCP servers as they're added
- Updating of routing hints when new servers are detected
- Maintenance of MCP server inventory automatically

### 7. Error Recovery

Each MCP server now includes:
- Implementation of automatic retry logic for failed MCP calls
- Tracking of failure rates per MCP server
- Suggestion of alternative MCP servers when primary fails

## MCP Server Inventory

### Core Infrastructure

#### aicarmine-codex-app (37 tools)
- Health check: `aicarmine_codex_ops_health`
- Fallback: Terminal commands if MCP fails
- Performance: Track tool call latency
- Security: Log all tool calls
- Configuration: Validate tool allowlist
- Auto-discovery: Monitor for new tools
- Error recovery: Retry up to 3 times

#### aicarmine-codex-ops (9 tools)
- Health check: `aicarmine_codex_ops_health`
- Fallback: Direct terminal commands
- Performance: Monitor service state queries
- Security: Audit service state access
- Configuration: Validate port mappings
- Auto-discovery: Detect new services
- Error recovery: Retry service state queries

### Repository Operations

#### aicarmine-repo-state (3 tools)
- Health check: `aicarmine_repo_state_health`
- Fallback: Git commands
- Performance: Track repo status queries
- Security: Audit repository state access
- Configuration: Validate repo root
- Auto-discovery: Detect new repositories
- Error recovery: Retry repo state queries

#### aicarmine-repo-search-det (8 tools)
- Health check: `aicarmine_repo_search_det_health`
- Fallback: ripgrep/fd commands
- Performance: Track search query latency
- Security: Audit search access patterns
- Configuration: Validate search allowlist
- Auto-discovery: Detect new search tools
- Error recovery: Retry search queries

#### aicarmine-repo-code (5 tools)
- Health check: `aicarmine_repo_code_health`
- Fallback: Git apply commands
- Performance: Track code edit latency
- Security: Audit code modifications
- Configuration: Validate patch sequencing
- Auto-discovery: Detect new code tools
- Error recovery: Retry code edits

#### aicarmine-repo-validate (9 tools)
- Health check: `aicarmine_repo_validate_health`
- Fallback: Direct validation commands
- Performance: Track validation query latency
- Security: Audit validation access
- Configuration: Validate validation allowlist
- Auto-discovery: Detect new validation tools
- Error recovery: Retry validation queries

#### aicarmine-git-readonly (6 tools)
- Health check: `aicarmine_git_readonly_health`
- Fallback: Git log/show commands
- Performance: Track git query latency
- Security: Audit git access patterns
- Configuration: Validate git allowlist
- Auto-discovery: Detect new git tools
- Error recovery: Retry git queries

### Runtime & Jobs

#### aicarmine-job-artifact (9 tools)
- Health check: `aicarmine_job_artifact_health`
- Fallback: Direct artifact access
- Performance: Track artifact query latency
- Security: Audit artifact access
- Configuration: Validate artifact paths
- Auto-discovery: Detect new artifact locations
- Error recovery: Retry artifact queries

#### aicarmine-job-view (8 tools)
- Health check: `aicarmine_job_view_health`
- Fallback: Direct HTML access
- Performance: Track view query latency
- Security: Audit view access patterns
- Configuration: Validate view allowlist
- Auto-discovery: Detect new view types
- Error recovery: Retry view queries

#### aicarmine-agentic-loop-client (7 tools)
- Health check: `aicarmine_agentic_loop_health`
- Fallback: Direct agentic loop calls
- Performance: Track agentic loop latency
- Security: Audit agentic loop access
- Configuration: Validate agentic loop ports
- Auto-discovery: Detect new agentic loops
- Error recovery: Retry agentic loop calls

#### aicarmine-local-subagent (3 tools)
- Health check: `aicarmine_local_subagent_health`
- Fallback: Direct subagent calls
- Performance: Track subagent query latency
- Security: Audit subagent access
- Configuration: Validate subagent ports
- Auto-discovery: Detect new subagents
- Error recovery: Retry subagent calls

#### aicarmine-broker-planner (8 tools)
- Health check: `aicarmine_broker_planner_health`
- Fallback: Direct planner calls
- Performance: Track planner query latency
- Security: Audit planner access
- Configuration: Validate planner state
- Auto-discovery: Detect new planner tools
- Error recovery: Retry planner calls

#### aicarmine-planner-components (5 tools)
- Health check: `aicarmine_planner_components_health`
- Fallback: Direct component calls
- Performance: Track component query latency
- Security: Audit component access
- Configuration: Validate component state
- Auto-discovery: Detect new components
- Error recovery: Retry component calls

### Data & Memory

#### aicarmine-project-memory (7 tools)
- Health check: `aicarmine_project_memory_health`
- Fallback: Direct memory access
- Performance: Track memory query latency
- Security: Audit memory access patterns
- Configuration: Validate memory allowlist
- Auto-discovery: Detect new memory locations
- Error recovery: Retry memory queries

#### aicarmine-sqlite-readonly (4 tools)
- Health check: `aicarmine_sqlite_readonly_health`
- Fallback: Direct SQLite queries
- Performance: Track query latency
- Security: Audit database access
- Configuration: Validate database allowlist
- Auto-discovery: Detect new databases
- Error recovery: Retry database queries

#### aicarmine-rag (3 tools)
- Health check: `aicarmine_rag_health`
- Fallback: Direct RAG queries
- Performance: Track RAG query latency
- Security: Audit RAG access
- Configuration: Validate RAG index
- Auto-discovery: Detect new RAG indexes
- Error recovery: Retry RAG queries

#### aicarmine-rag-router (7 tools)
- Health check: `aicarmine_rag_router_health`
- Fallback: Direct RAG router calls
- Performance: Track router query latency
- Security: Audit router access
- Configuration: Validate router configuration
- Auto-discovery: Detect new routers
- Error recovery: Retry router calls

### Model & Inference

#### aicarmine-ollama (13 tools)
- Health check: `aicarmine_ollama_health`
- Fallback: Direct Ollama calls
- Performance: Track model query latency
- Security: Audit model access
- Configuration: Validate model allowlist
- Auto-discovery: Detect new models
- Error recovery: Retry model calls

#### aicarmine-ovms-reranker (8 tools)
- Health check: `aicarmine_ovms_health`
- Fallback: Direct reranker calls
- Performance: Track reranker query latency
- Security: Audit reranker access
- Configuration: Validate reranker configuration
- Auto-discovery: Detect new rerankers
- Error recovery: Retry reranker calls

## Implementation

All improvements are implemented in the following files:
- `.clinerules/hooks/lib/aicarmine_cline_task_bootstrap.ps1`
- `.clinerules/hooks/lib/aicarmine_cline_pretool_observer.ps1`
- `.clinerules/hooks/lib/aicarmine_cline_mcp_router.ps1`
- `.clinerules/hooks/lib/aicarmine_cline_posttool_observer.ps1`
- `.clinerules/hooks/lib/aicarmine_cline_precompact_continuity.ps1`
- `.clinerules/hooks/lib/aicarmine_cline_contract_probe.ps1`

## Benefits

1. **Improved reliability**: Automatic health checks and error recovery
2. **Better performance**: Latency tracking and optimization recommendations
3. **Enhanced security**: Complete audit trail and access pattern tracking
4. **Future-proof**: Auto-discovery and configuration validation
5. **Reduced friction**: Fallback logging and recommendations