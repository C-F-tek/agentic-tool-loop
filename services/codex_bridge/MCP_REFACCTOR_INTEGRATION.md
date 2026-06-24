# MCP Complete Surface Integration Guide — 19 Servers

## Overview

This document describes the complete integration of **19 MCP servers** into the AICarmine Cline ecosystem. The system provides repository tools, refactoring utilities, data queries, job diagnostics, and agent clients.

---

## Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `refactor_tools.py` | `services/codex_bridge/refactor_tools.py` | Core refactoring utilities (libcst, rope, bowler) |
| `refactor_mcp_server.py` | `services/codex_bridge/refactor_mcp_server.py` | Refactoring MCP server wrapper |
| `mcp.json` | `%APPDATA%\Code\User\mcp.json` | Cline MCP configuration |
| `aicarmine_cline_mcp_router.ps1` | `.clinerules/hooks/lib/aicarmine_cline_mcp_router.ps1` | Cline hook routing |
| `aicarmine_cline_task_bootstrap.ps1` | `.clinerules/hooks/lib/aicarmine_cline_task_bootstrap.ps1` | Task bootstrap hook |
| `AGENTS.md` | `AGENTS.md` | Global agent instructions |
| `ops_mcp_server.py` | `services/codex_bridge/ops_mcp_server.py` | LOCAL_MCP_SERVERS allowlist |

---

## Complete MCP Server Inventory (19 Total)

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

### Operations & Discovery Tools (4 servers, 23 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 11 | `aicarmine_codex_ops` | ops_mcp_server.py | 7 | MCP inventory probe, service state snapshot |
| 12 | `aicarmine_repo_symbol_index` | repo_symbol_index_mcp_server.py | 4 | Symbol indexing, query, summary |
| 13 | `aicarmine_test_discovery` | test_discovery_mcp_server.py | 5 | Discover patterns, find uncovered, generate scaffolds |
| 14 | `aicarmine_code_dep_graph` | code_dep_graph_mcp_server.py | 7 | Build dep graph, find chains, detect cycles, callers, dependents, breakage risk |

### Refactoring Tools (1 server, 8 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 15 | `aicarmine_refactor` | refactor_mcp_server.py | 8 | libcst rename, rope cross-file rename, bowler git-rollback, git-tracked scope-aware refactoring |

### Agent & Loop Clients (3 servers, 14 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 16 | `aicarmine_local_subagent` | local_subagent_mcp_server.py | 3 | Local subagent with port 3579 |
| 17 | `aicarmine_agentic_loop_client` | agentic_loop_client_mcp_server.py | 7 | Agentic loop client with port 3579 |
| 18 | `aicarmine_ollama_subagent` | ollama_subagent_mcp_server.py | 4 | Ollama subagent with GPU (port 11435) |

### Code Format Tools (5 servers, 5 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 19 | `aicarmine_prettier` | prettier_mcp_server.py | 1 | Prettier code formatter |
| 20 | `aicarmine_biome` | biome_mcp_server.py | 1 | Biome linter/formatter |
| 21 | `aicarmine_ruff` | ruff_mcp_server.py | 1 | Ruff linter |
| 22 | `aicarmine_eslint` | eslint_mcp_server.py | 1 | ESLint linter |
| 23 | `aicarmine_black` | black_mcp_server.py | 1 | Black code formatter |

**Total: 19 servers, ~89 tools across all servers**


---

## MCP Server Configuration

### mcp.json Entry (All 19 Servers)

The complete `mcp.json` configuration is maintained at `%APPDATA%\Code\User\mcp.json`. Key entries include:

```json
{
  "aicarmine_refactor": {
    "type": "stdio",
    "command": "C:\\Users\\carmi\\AI\\venvs\\labtools\\Scripts\\python.exe",
    "args": ["-u", "C:\\Users\\carmi\\AI\\services\\codex_bridge\\refactor_mcp_server.py"],
    "cwd": "C:\\Users\\carmi\\AI",
    "env": {
      "AICARMINE_CODEX_MCP_REPO_ROOT": "C:\\Users\\carmi\\AI",
      "AICARMINE_LAB_REPO": "C:\\Users\\carmi\\AI",
      "AICARMINE_USEFUL_TOOLS_ROOT": "C:\\Users\\carmi\\AI\\services\\useful_tools",
      "AICARMINE_REPO_MCP_MAX_TEXT_CHARS": "24000"
    }
  }
}
```

---

## Available MCP Tools

### 1. `refactor_rename_symbol`

**Description:** Single-file rename via libcst (AST-aware)

**Arguments:**
```json
{
  "file": "services/codex_bridge/refactor_tools.py",
  "old_name": "old_function",
  "new_name": "new_function"
}
```

**Use case:** Fast single-file symbol renaming with guaranteed syntactic correctness.

---

### 2. `refactor_rename_symbol_rope`

**Description:** Cross-file rename via rope (project-wide)

**Arguments:**
```json
{
  "file": "services/codex_bridge/refactor_tools.py",
  "old_name": "old_function",
  "new_name": "new_function",
  "project_root": "."
}
```

**Use case:** Renaming symbols that appear across multiple files in a project.

---

### 3. `refactor_add_parameter`

**Description:** Add keyword parameter to matching function calls

**Arguments:**
```json
{
  "file": "services/codex_bridge/mcp_server.py",
  "func_name": "handle_request",
  "param_name": "server_name",
  "param_value": "refactor-mcp"
}
```

**Use case:** Adding new parameters to existing function calls without breaking signatures.

---

### 4. `refactor_extract_function`

**Description:** Extract code block into new function via rope

**Arguments:**
```json
{
  "file": "services/codex_bridge/mcp_server.py",
  "start_line": 100,
  "end_line": 120,
  "function_name": "process_request"
}
```

**Use case:** Refactoring long functions by extracting reusable code blocks.

---

### 5. `refactor_rename_project` ⭐

**Description:** Rename across git-tracked files only (respects .gitignore)

**Arguments:**
```json
{
  "old_name": "OldClassName",
  "new_name": "NewClassName",
  "root_dir": ".",
  "scope": "tracked"
}
```

**Scope options:**
- `tracked` — Only git-tracked files (default, respects .gitignore)
- `staged` — Only staged files (git add)
- `modified` — Only modified working tree files
- `all` — All Python files including untracked

**Use case:** Safe project-wide renaming that excludes external packages and build artifacts.

---

### 6. `refactor_rename_project_bowler` ⭐

**Description:** Rename with bowler + automatic git rollback support

**Arguments:**
```json
{
  "old_name": "OldClassName",
  "new_name": "NewClassName",
  "root_dir": ".",
  "scope": "tracked",
  "dry_run": true
}
```

**Use case:** AST-aware renaming with automatic git diff and rollback capabilities. Always use `dry_run=true` first to preview changes before applying.

---

### 7. `git_list_tracked_files`

**Description:** List all git-tracked Python files in repository

**Arguments:**
```json
{
  "root_dir": "."
}
```

**Use case:** Inspecting which files will be affected by scope-aware refactoring operations.

---

### 8. `refactor_health`

**Description:** Check refactoring tool availability

**Arguments:** None (empty object)

**Response:**
```json
{
  "libcst_available": true,
  "rope_available": true,
  "bowler_available": true,
  "message": "Refactoring tools ready"
}
```

---

## Cline Hook Integration

### MCP Router Detection

The Cline hook (`aicarmine_cline_mcp_router.ps1`) automatically detects refactoring tasks and routes them to the appropriate MCP tools:

**Detection triggers:**
- Keywords: `refactor`, `rename symbol`, `AST transformation`, `code refactoring`, `symbol rename`, `cross-file rename`, `git-tracked files`, `.gitignore`, `scope=tracked`
- Tool names: `libcst`, `rope`, `bowler`

**Priority:** `repository_refactor` has tie order 2, meaning it takes high priority in tool selection.

**Routing constraints added:**
```
- Use scope=tracked for project-wide renames to exclude external packages.
- Prefer dry_run=true first, then dry_run=false to apply changes.
```

---

## AGENTS.md Integration

### Refactoring MCP Skill

The global `AGENTS.md` now includes the "Refactoring MCP Skill" section:

1. Use `aicarmine_refactor` MCP server for all Python refactoring operations.
2. Always use `scope="tracked"` for project-wide renames to exclude external packages and respect `.gitignore`.
3. For safe refactoring with rollback support, prefer `refactor_rename_project_bowler` with `dry_run=true` first, then `dry_run=false` to apply.

---

## Usage Examples

### Via MCP Client (JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "refactor_rename_project",
    "arguments": {
      "old_name": "OldClassName",
      "new_name": "NewClassName",
      "root_dir": ".",
      "scope": "tracked"
    }
  }
}
```

### Via Python API

```python
from services.codex_bridge.refactor_tools import (
    refactor_rename_symbol,
    refactor_rename_project,
    refactor_rename_project_bowler,
)

# Single file rename (libcst)
result = refactor_rename_symbol(
    "services/codex_bridge/refactor_tools.py",
    "old_function",
    "new_function",
)

# Project-wide rename (git-tracked only)
results = refactor_rename_project(
    "OldClass",
    "NewClass",
    root_dir=".",
    scope="tracked",  # Respects .gitignore
)

# Bowler with git rollback
results = refactor_rename_project_bowler(
    "OldClass",
    "NewClass",
    root_dir=".",
    scope="tracked",
    dry_run=True,  # Preview first
)
```

---

## File Exclusions

The refactoring tools automatically exclude these patterns:

- `site-packages`, `__pycache__`, `.venv`, `venv`, `node_modules`
- `.git`, `*.egg-info`, `*.pyc`, `*.pyo`, `*.so`, `*.dylib`
- `*.dll`, `*.exe`, `.pytest_cache`, `.mypy_cache`, `htmlcov`, `coverage.xml`
- `.tox`, `.nox`

---

## Installation Verification

```bash
python -m py_compile services/codex_bridge/refactor_tools.py    # OK
python -m py_compile services/codex_bridge/refactor_mcp_server.py  # OK
```

---

## Cline Hook Integration

### Task Bootstrap Hook (`aicarmine_cline_task_bootstrap.ps1`)

Reports 19 MCP servers categorized into:
- Core (4), Data (3), Jobs (3), Ops (4), Refactor (1), Agents (3)

### MCP Router Hook (`aicarmine_cline_mcp_router.ps1`)

Automatically detects task classes and routes to appropriate tools:
- `repository_validation` → repo_validate tools
- `repository_patch` → repo_code tools
- `repository_refactor` → refactor tools (NEW, priority 2)
- `repository_search` → repo_search_det tools
- `project_memory` → project_memory tools
- `repository_state` → repo_state tools
- `git_readonly` → git_readonly tools
- `job_diagnostics` → job_artifact/job_view tools

---

## Known Limitations

1. **Bowler CLI dependency:** The bowler integration uses subprocess calls to the bowler CLI. Ensure bowler is installed (`pip install bowler`).
2. **Git repository required:** Scope-aware operations (`tracked`, `staged`, `modified`) require a valid git repository with tracked files.
3. **libcst single-file only:** The libcst-based `refactor_rename_symbol` operates on a single file at a time. Use rope or bowler for cross-file renames.
4. **Agent clients:** `aicarmine_local_subagent` and `aicarmine_agentic_loop_client` explicitly delegate to broker (port 3579) and are not read-only.
