# MCP Complete Surface Integration Guide — 20 Servers

## Overview

This document describes the complete integration of **20 MCP servers** into the AICarmine Cline ecosystem. The system provides repository tools, refactoring utilities, data queries, job diagnostics, index management, and agent clients.

---

## Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `refactor_tools.py` | `services/codex_bridge/refactor_tools.py` | Core refactoring utilities (libcst, rope, bowler) |
| `refactor_mcp_server.py` | `services/codex_bridge/refactor_mcp_server.py` | Refactoring MCP server wrapper |
| `index_bridge_mcp_server.py` | `services/codex_bridge/index_bridge_mcp_server.py` | Cross-reference RAG + Symbol Index |
| `repo_mcp_common.py` | `services/codex_bridge/repo_mcp_common.py` | Shared utilities (string_prop, integer_prop, boolean_prop, etc.) |
| `mcp.json` | `%APPDATA%\Code\User\mcp.json` | Cline MCP configuration |
| `cline_mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` | Cline MCP settings with autoApprove |
| `aicarmine_cline_mcp_router.ps1` | `.clinerules/hooks/lib/aicarmine_cline_mcp_router.ps1` | Cline hook routing |
| `aicarmine_cline_task_bootstrap.ps1` | `.clinerules/hooks/lib/aicarmine_cline_task_bootstrap.ps1` | Task bootstrap hook |
| `AGENTS.md` | `AGENTS.md` | Global agent instructions |
| `ops_mcp_server.py` | `services/codex_bridge/ops_mcp_server.py` | LOCAL_MCP_SERVERS allowlist |

---

## Complete MCP Server Inventory (20 Total)

### Core Repository Tools (4 servers, 25 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 1 | `aicarmine_repo_state` | repo_state_mcp_server.py | 3 | Health, status, capabilities |
| 2 | `aicarmine_repo_search_det` | repo_search_det_mcp_server.py | 8 | fd, rg, ast-grep, ctags, jq, tree-sitter |
| 3 | `aicarmine_repo_validate` | repo_validate_mcp_server.py | 9 | ruff, pyright, semgrep, shellcheck, pytest, probes |
| 4 | `aicarmine_repo_code` | repo_code_mcp_server.py | 5 | propose_edit, apply_patch, git_apply_check, unidiff_validate |

### Data & Query Tools (3 servers, 14 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 5 | `aicarmine_rag` | rag_mcp_server.py | 3 | RAG search, index management, reindexing |
| 6 | `aicarmine_sqlite_readonly` | sqlite_readonly_mcp_server.py | 4 | Query, schema, list databases |
| 7 | `aicarmine_project_memory` | project_memory_mcp_server.py | 7 | Search, get, upsert, mark_stale, supersede |

### Job & Artifact Tools (3 servers, 23 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 8 | `aicarmine_job_artifact` | job_artifact_mcp_server.py | 9 | Events, final, tool results, planner payloads |
| 9 | `aicarmine_job_view` | job_view_mcp_server.py | 8 | HTML rendering, IA payload, validation |
| 10 | `aicarmine_git_readonly` | git_readonly_mcp_server.py | 6 | log, show, diff, blame, branch_compare |

### Operations & Discovery Tools (5 servers, 28 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 11 | `aicarmine_codex_ops` | ops_mcp_server.py | 7 | MCP inventory probe, service state snapshot |
| 12 | `aicarmine_repo_symbol_index` | repo_symbol_index_mcp_server.py | 4 | Symbol indexing, query, summary |
| 13 | `aicarmine_test_discovery` | test_discovery_mcp_server.py | 5 | Discover patterns, find uncovered, generate scaffolds |
| 14 | `aicarmine_code_dep_graph` | code_dep_graph_mcp_server.py | 7 | Build dep graph, find chains, detect cycles, callers, dependents, breakage risk |
| 15 | `aicarmine_index_bridge` | index_bridge_mcp_server.py | 5 | Cross-reference RAG + Symbol Index, unified search, persistent memory |

### Refactoring Tools (1 server, 8 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 16 | `aicarmine_refactor` | refactor_mcp_server.py | 8 | libcst rename, rope cross-file rename, bowler git-rollback, git-tracked scope-aware refactoring |

### Agent & Loop Clients (3 servers, 14 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 17 | `aicarmine_local_subagent` | local_subagent_mcp_server.py | 3 | Local subagent with port 3579 |
| 18 | `aicarmine_agentic_loop_client` | agentic_loop_client_mcp_server.py | 7 | Agentic loop client with port 3579 |
| 19 | `aicarmine_ollama_subagent` | ollama_subagent_mcp_server.py | 4 | Ollama subagent with GPU (port 11435) |

### Code Format Tools (1 server, 1 tool)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 20 | `aicarmine_prettier` | prettier_mcp_server.py | 1 | Prettier code formatter |

**Total: 20 servers, ~89 tools across all servers**

---

## Index Bridge Tools

### 1. `aicarmine_index_bridge_health`

**Description:** Report index bridge MCP health and DB status.

**Arguments:** None (empty object)

**Response:**
```json
{
  "ok": true,
  "server": "aicarmine-index-bridge-mcp",
  "index_bridge": {
    "enabled": true,
    "bridge_db": "C:\\Users\\carmi\\AI\\state\\index_bridge\\bridge.sqlite3",
    "rag_db": "C:\\Users\\carmi\\AI\\state\\codex_rag\\code_rag.sqlite3",
    "symbol_db": "C:\\Users\\carmi\\AI\\state\\symbol_index\\symbols.sqlite3"
  }
}
```

### 2. `aicarmine_index_bridge_build` ⭐

**Description:** Build cross-reference tables from existing RAG + Symbol Index DBs (no re-indexing).

**Arguments:** None (empty object)

**Response:**
```json
{
  "ok": true,
  "bridge_db": "C:\\Users\\carmi\\AI\\state\\index_bridge\\bridge.sqlite3",
  "unified_index_count": 6533,
  "chunk_symbol_refs": 763,
  "persistent_memory_records": 0,
  "message": "Bridge built from existing RAG + Symbol Index DBs (no re-indexing)"
}
```

### 3. `aicarmine_index_bridge_query`

**Description:** Query across both RAG and Symbol Index via the bridge.

**Arguments:**
```json
{
  "query": "handle_request",
  "source": "all",
  "limit": 20
}
```

**Source options:** `all`, `rag`, `symbol`

### 4. `aicarmine_index_bridge_persist`

**Description:** Persist symbol memory across server restarts.

**Arguments:**
```json
{
  "key": "my_key",
  "value": "my_value",
  "scope": "repo",
  "source_type": "user",
  "source_ref": ""
}
```

### 5. `aicarmine_index_bridge_get_memory`

**Description:** Retrieve persisted symbol memory.

**Arguments:**
```json
{
  "key": "my_key",
  "scope": "repo"
}
```

---

## Cline Hook Integration

### MCP Router Detection

The Cline hook (`aicarmine_cline_mcp_router.ps1`) automatically detects task classes and routes to appropriate tools:

**Detection triggers:**
- `repository_validation` → repo_validate tools (ruff, pyright, semgrep, probes)
- `repository_patch` → repo_code tools (propose_edit, apply_patch, git_apply_check)
- `repository_refactor` → refactor tools (libcst, rope, bowler)
- `repository_search` → repo_search_det tools (fd, rg, ast-grep, ctags)
- `project_memory` → project_memory tools (search, get, upsert, mark_stale)
- `semantic_search` → RAG + index_bridge tools (context search, bridge build/query)
- `code_analysis` → dep graph, symbol index, test discovery

**Routing constraints added:**
```
- Before calling propose_edit, read the target file first to get actual working-tree content.
- Use exact old_text from the actual file; do not guess or use stale anchors.
- If anchor_not_found error occurs, re-read the file and retry with correct anchors.
- ast-grep patterns use sgtree syntax (e.g. "class $IDENTIFIER:", "def $FUNC($PARAMS) -> $RET:").
- Do not use regex-like patterns; ast-grep uses its own pattern language with variable prefixes like $VAR.
```

---

## AGENTS.md Integration

### Refactoring MCP Skill

The global `AGENTS.md` includes the "Refactoring MCP Skill" section:

1. Use `aicarmine_refactor` MCP server for all Python refactoring operations.
2. Always use `scope="tracked"` for project-wide renames to exclude external packages and respect `.gitignore`.
3. For safe refactoring with rollback support, prefer `refactor_rename_project_bowler` with `dry_run=true` first, then `dry_run=false` to apply.

### Index Bridge Usage

When tasks involve index cross-referencing:

1. Use `aicarmine_index_bridge_health` to verify DB availability
2. Use `aicarmine_index_bridge_build` to build/update cross-reference tables
3. Use `aicarmine_index_bridge_query` to search across both RAG + Symbol Index
4. Use `aicarmine_index_bridge_persist`/`get_memory` for persistent symbol memory

---

## Available MCP Tools

### Refactoring Tools (from aicarmine_refactor)

| Tool | Description | Key Feature |
|------|-------------|-------------|
| `refactor_rename_symbol` | Single-file rename via libcst | AST-aware, guaranteed syntactic correctness |
| `refactor_rename_symbol_rope` | Cross-file rename via rope | Project-wide symbol renaming |
| `refactor_add_parameter` | Add keyword parameter to function calls | Safe signature modification |
| `refactor_extract_function` | Extract code block into new function | Code extraction via rope |
| `refactor_rename_project` | Rename across git-tracked files | Respects `.gitignore`, scope=tracked |
| `refactor_rename_project_bowler` | Rename with bowler + git rollback | AST-aware with automatic rollback support |
| `git_list_tracked_files` | List all git-tracked Python files | File inventory for scope-aware ops |
| `refactor_health` | Check refactoring tool availability | Verify libcst, rope, bowler status |

### Shared Utilities (from repo_mcp_common.py)

All MCP servers now import from the shared utilities module:

- `string_prop(default)` — JSON Schema string property
- `integer_prop(default, minimum, maximum)` — JSON Schema integer property
- `boolean_prop(default)` — JSON Schema boolean property
- `safe_int(value, default, low, high)` — Safe int conversion with bounds
- `safe_float(value, default)` — Safe float conversion
- `safe_bool(value, default)` — Safe bool conversion
- `json_dumps(value, compact)` — JSON serialization
- `compact_text(text, limit)` — Text compaction
- `tool_content(text)` — Formatted tool content
- `ok(...) / err(...)` — JSON-RPC response builders
- `handle_request(request, tools)` — Request handler
- `serve(server_name, server_version, tools)` — stdio message loop

---

## File Exclusions

The refactoring tools automatically exclude these patterns:

- `site-packages`, `__pycache__`, `.venv`, `venv`, `node_modules`
- `.git`, `*.egg-info`, `*.pyc`, `*.pyo`, `*.so`, `*.dylib`
- `*.dll`, `*.exe`, `.pytest_cache`, `.mypy_cache`, `htmlcov`, `coverage.xml`
- `.tox`, `.nox`

---

## Index Operations Guide

### Reindex RAG (Full)

```
Tool: aicarmine_rag_reindex
Arguments: {"source": "git", "mode": "full"}
```

Respects `.gitignore` via `git ls-files --cached --others --exclude-standard`.

### Build Symbol Index (Full)

```
Tool: aicarmine_repo_symbol_index_build
Arguments: {"path": ".", "language": "python", "persist": true}
```

Scans git-tracked Python files and extracts symbol definitions.

### Build Index Bridge

```
Tool: aicarmine_index_bridge_build
Arguments: {}
```

Reads from existing RAG + Symbol Index DBs without re-indexing files.

---

## Installation Verification

```bash
python -m py_compile services/codex_bridge/refactor_tools.py    # OK
python -m py_compile services/codex_bridge/refactor_mcp_server.py  # OK
python -m py_compile services/codex_bridge/index_bridge_mcp_server.py  # OK
python -m py_compile services/codex_bridge/repo_mcp_common.py  # OK
```

---

## Known Limitations

1. **Bowler CLI dependency:** The bowler integration uses subprocess calls to the bowler CLI. Ensure bowler is installed (`pip install bowler`).
2. **Git repository required:** Scope-aware operations (`tracked`, `staged`, `modified`) require a valid git repository with tracked files.
3. **libcst single-file only:** The libcst-based `refactor_rename_symbol` operates on a single file at a time. Use rope or bowler for cross-file renames.
4. **Agent clients:** `aicarmine_local_subagent` and `aicarmine_agentic_loop_client` explicitly delegate to broker (port 3579) and are not read-only.
5. **Index bridge DB path:** Requires both RAG DB and Symbol Index DB to exist before building the bridge.