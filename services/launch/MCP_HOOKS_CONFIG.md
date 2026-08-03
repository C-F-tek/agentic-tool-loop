# MCP Hooks Configuration

## Overview

This document defines the automatic MCP routing hooks that enhance Cline's awareness and automatic usage of MCP servers based on task patterns.

## Hook System

### Hook 1: Pattern Matching Hooks

When a task matches these patterns, the corresponding MCP server is automatically selected:

| Pattern | MCP Server | Tool Category |
|---------|------------|---------------|
| `find files`, `search repo`, `grep`, `rg` | aicarmine-repo-search-det | fd, ripgrep, ast-grep |
| `edit code`, `patch`, `structured_edit` | aicarmine-repo-code | structured_edit, unified_diff |
| `validate`, `lint`, `ruff`, `pyright` | aicarmine-repo-validate | ruff, pyright, semgrep |
| `git log`, `git diff`, `git blame` | aicarmine-git-readonly | log, show, diff, blame |
| `job events`, `job artifacts`, `tool results` | aicarmine-job-artifact | events, final, tool_results |
| `job dashboard`, `HTML view`, `planner lab` | aicarmine-job-view | render, ia_view |
| `memory`, `project memory`, `upsert` | aicarmine-project-memory | search, upsert, supersede |
| `sqlite`, `query`, `schema` | aicarmine-sqlite-readonly | list_databases, query |
| `RAG`, `context search`, `index` | aicarmine-rag | context, reindex |
| `RAG router`, `cross-DB`, `query plan` | aicarmine-rag-router | analyze_query, consolidate_plan |
| `Ollama`, `model chat`, `generate` | aicarmine-ollama | chat, generate |
| `rerank`, `OVMS`, `BGE` | aicarmine-ovms-reranker | rerank, config |
| `agentic loop`, `broker run`, `vulkan` | aicarmine-agentic-loop-client | run, status, result |
| `subagent`, `bounded task`, `read-only` | aicarmine-local-subagent | run_readonly |
| `planner state`, `decision history` | aicarmine-broker-planner | state, decisions |
| `service state`, `ports`, `processes` | aicarmine-codex-ops | snapshot, ports |

### Hook 2: Confirmation Tokens

Each MCP server requires explicit confirmation tokens before execution:

- `aicarmine_agentic_loop_run` → Agentic loop execution
- `aicarmine_agentic_loop_status` → Agentic loop status check
- `aicarmine_agentic_loop_result` → Agentic loop result retrieval
- `aicarmine_agentic_loop_ensure_broker` → Broker startup
- `aicarmine_agentic_loop_ensure_reranker` → Reranker startup
- `aicarmine_repo_code_apply_patch` → Patch application
- `aicarmine_project_memory_upsert_verified` → Memory write
- `aicarmine_project_memory_mark_stale` → Memory stale marking
- `aicarmine_project_memory_supersede` → Memory superseding

### Hook 3: Runtime Port Hooks

When a task involves these ports, the corresponding service is automatically identified:

| Port | Service | Hook |
|------|---------|------|
| 3550 | OVMS Reranker | Check ovms.exe process |
| 3571 | Vulkan Bridge | Check uvicorn on port 3571 |
| 3572 | Vulkan Tool Broker | Check uvicorn on port 3572 |
| 3579 | Agentic Loop Client | Check uvicorn on port 3579 |
| 11434 | Ollama | Check ollama.exe process |

## Automatic Discovery

The hook system automatically discovers MCP servers via:

1. `aicarmine_mcp_inventory_list_targets` → List all registered MCP servers
2. `aicarmine_mcp_inventory_probe` → Probe each server for health and tools
3. `aicarmine_service_state_snapshot` → Capture ports, processes, logs

## Usage Examples

### Example 1: Repository Search
```
Task: "Find all Python files containing 'TODO'"
→ Hook triggers: aicarmine-repo-search-det (ripgrep)
```

### Example 2: Code Editing
```
Task: "Fix the syntax error in services/codex_bridge/mcp_server.py"
→ Hook triggers: aicarmine-repo-code (structured_edit)
```

### Example 3: Job Inspection
```
Task: "Show me the events from job-123"
→ Hook triggers: aicarmine-job-artifact (events)
```

### Example 4: Model Chat
```
Task: "Generate a Python function for sorting"
→ Hook triggers: aicarmine-ollama (chat)
```

## Configuration

All hooks are configured in:
- `cline_mcp_servers.json` → MCP server definitions
- `AGENTS.md` → Routing patterns and precedence
- `MCP_SERVERS_ANALYSIS.md` → Complete server inventory

## Benefits

1. **Automatic routing**: Tasks are automatically routed to the correct MCP server
2. **Reduced friction**: No manual server selection required
3. **Consistency**: Same patterns applied across all tasks
4. **Awareness**: Full inventory of 95 tools across 16 servers