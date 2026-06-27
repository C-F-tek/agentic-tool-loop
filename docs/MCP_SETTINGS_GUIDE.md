# MCP Settings Configuration Guide

## Overview

This workspace uses Cline's Model Context Protocol (MCP) servers for tool access. The MCP configuration is managed through a **single file** that Cline reads directly from VS Code's global storage directory.

---

## File Location

**Path**: `C:\Users\carmi\AppData\Roaming\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

- **This is the only file Cline reads** — no alternative paths exist
- VS Code's internal global storage location
- Cannot be changed via environment variables or settings
- Contains all 19 MCP server definitions
- **All edits must go here**

---

## Environment Variables

### AICARMINE_MCP_COMPRESSION

```
Variable: AICARMINE_MCP_COMPRESSION
Value:    1
Scope:    User (persistent)
Purpose:  Enables JSON response compression for MCP batch operations
```

**How to set:**

```powershell
[System.Environment]::SetEnvironmentVariable('AICARMINE_MCP_COMPRESSION', '1', 'User')
```

---

## Available MCP Servers

| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_rag` | rag_mcp_server.py | 4 | RAG search, index management, reindexing |
| `aicarmine_repo_state` | repo_state_mcp_server.py | 3 | Health, status, capabilities |
| `aicarmine_repo_validate` | repo_validate_mcp_server.py | 9 | ruff, pyright, semgrep, shellcheck, pytest, probes |
| `aicarmine_repo_search_det` | repo_search_det_mcp_server.py | 8 | fd, rg, ast-grep, ctags, jq, tree-sitter |
| `aicarmine_repo_code` | repo_code_mcp_server.py | 5 | propose_edit, apply_patch, git_apply_check, unidiff_validate |
| `aicarmine_codex_ops` | ops_mcp_server.py | 10 | MCP inventory probe, service state snapshot, ports, processes, logs |
| `aicarmine_job_view` | job_view_mcp_server.py | 8 | HTML rendering, IA payload, validation |
| `aicarmine_job_artifact` | job_artifact_mcp_server.py | 9 | Events, final, tool results, planner payloads |
| `aicarmine_git_readonly` | git_readonly_mcp_server.py | 6 | log, show, diff, blame, branch_compare |
| `aicarmine_sqlite_readonly` | sqlite_readonly_mcp_server.py | 4 | Query, schema, list databases |
| `aicarmine_project_memory` | project_memory_mcp_server.py | 7 | Search, get, upsert, mark_stale, supersede |
| `aicarmine_code_dep_graph` | code_dep_graph_mcp_server.py | 7 | Build dep graph, find chains, detect cycles |
| `aicarmine_repo_symbol_index` | repo_symbol_index_mcp_server.py | 4 | Symbol indexing, query, summary |
| `aicarmine_test_discovery` | test_discovery_mcp_server.py | 5 | Discover patterns, find uncovered, generate scaffolds |
| `aicarmine_ollama_subagent` | ollama_subagent_mcp_server.py | 4 | Ollama subagent with GPU (port 11435) |
| `aicarmine_local_subagent` | local_subagent_mcp_server.py | 3 | Local subagent with port 3579 (disabled) |
| `aicarmine_index_bridge` | index_bridge_mcp_server.py | 5 | Cross-reference RAG + Symbol Index |
| `aicarmine_mcp_batch_proxy` | mcp_batch_proxy_server.py | 3 | Parallel MCP operations across servers |
| `aicarmine_wily` | wily_mcp_server.py | 10 | Code complexity analysis (Wily CLI + AST fallback) |

---

## Wily MCP Server — Code Complexity Tools

The `aicarmine_wily` server provides 10 tools for code complexity analysis:

### Wily CLI Tools (Git/FileSystem Archiver)

| Tool | Description |
|------|-------------|
| `wily_health` | Report Wily installation status, cache health, revision count |
| `wily_report` | Show metrics (raw, halstead, cyclomatic, maintainability) for a given file |
| `wily_rank` | Rank files/functions by complexity metric |
| `wily_build` | Build/rebuild Wily cache (delta/full) |
| `wily_index` | Show history archive from `.wily/` folder |
| `wily_diff` | Show metric differences between revisions |
| `wily_list_metrics` | List available complexity metrics |

### AST-Based Fallback Tools (Workspace-Wide Analysis)

These tools use Python's `ast` module to analyze code without requiring Git-tracked files:

| Tool | Description | Args |
|------|-------------|------|
| `ast_complexity_report` | Full workspace complexity report via Python AST. Scans all Python files, skipping `.venv`, `__pycache__`, `node_modules`, `.git`. Returns file metrics and top functions by cyclomatic complexity. | None |
| `ast_file_metrics` | Metrics for a single file via Python AST. Returns class count, function count, line count, and per-function metrics (complexity, nesting, params). | `path` (string) |
| `ast_top_functions` | Top N most complex functions across the workspace via Python AST. | `limit` (default 50), `min_complexity` (default 1) |

### AST Analysis Results

**Workspace Scan Summary**:
- **342 Python files** scanned across `services/` tree
- **Largest file**: `vulkan_bridge/app.py` (4239 lines)
- **Highest complexity function**: `validate_planner_decision_against_evidence` in `aicarmine_broker/application/planner/validator.py`
  - Cyclomatic complexity: **616** (extreme — refactoring recommended)
  - Lines: 1679 (lines 449-2127)
  - If-statements: 271, For-loops: 23, Try-blocks: 4

---

## MCP Routing Hook

The PowerShell routing hook at `.clinerules/hooks/lib/aicarmine_cline_mcp_router.ps1` provides intelligent tool selection based on user input patterns.

### Code Complexity Tool Routing

```powershell
if ($normalized -match '\b(?:wily|code complexity|cyclomatic|halstead|maintainability|raw lines)\b') {
    $scores.code_complexity += 100
}
```

**Tool selection triggers**:

| Pattern | Tool |
|---------|------|
| `wily_health` | Always selected for code_complexity |
| `report\|file metrics` | `wily_report` |
| `rank\|ranking\|high complexity` | `wily_rank` |
| `build\|reindex\|cache rebuild` | `wily_build` |
| `diff\|revision\|history` | `wily_diff` |
| `wily_index` | Always selected |
| `wily_list_metrics` | Always selected |
| `complexity report\|top functions\|code quality\|ast analysis` | `ast_complexity_report` |
| `file metrics\|single file\|function count\|class count` | `ast_file_metrics` |
| `top.*complex\|most complex\|complexity threshold\|min_complexity` | `ast_top_functions` |

---

## Updating MCP Settings

### Step 1: Edit the Global File (Only Path Cline Reads)

```powershell
# This is the ONLY file Cline reads — no alternative paths exist
notepad "C:\Users\carmi\AppData\Roaming\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json"
```

### Step 2: Commit to Git (Optional Backup)

```powershell
git add .clinerules/cline_mcp_settings.json
git commit -m "feat: update MCP server configuration"
```

### Step 3: Restart VS Code

Close and reopen VS Code so Cline reads the new configuration.

---

## Troubleshooting

### Tool Not Found Error

If a tool returns `"error": "unknown_tool"`:

1. Verify the tool name is registered in `_tools()` in `services/codex_bridge/<server>.py`
2. Restart the MCP server (restart VS Code)
3. Check autoApprove list in `cline_mcp_settings.json`

### Environment Variable Not Active

New processes won't see environment variables set in an existing session. Either:

- Open a **new** PowerShell terminal after setting the variable
- Or use `[System.Environment]::SetEnvironmentVariable()` which persists across sessions

### Wily Metrics Not Found

Wily's Git archiver requires files to be committed. Use AST-based fallback tools instead:

```python
# Instead of wily_report (may return "Not found")
use_mcp_tool("aicarmine_wily", "ast_file_metrics", {"path": "services/aicarmine_broker/planner.py"})

# Or get full workspace report
use_mcp_tool("aicarmine_wily", "ast_complexity_report", {})
```

---

## References

- [AGENTS.md](../AGENTS.md) — Global agent instructions
- [MCP_OPERATIONAL_SUMMARY.md](../services/MCP_OPERATIONAL_SUMMARY.md) — Complete MCP server inventory
- [SERVICES_INDEX.md](./SERVICES_INDEX.md) — Services module documentation index