---
name: aicarmine-mcp-tool-priority
description: 'Offline skill for Cline AI assistant. Enforces MCP > native tool priority for repository operations. Use this when the AI assistant needs guidance on which tools to prefer.'
metadata:
  version: 1.0.0
---

# MCP Tool Priority Rule

## Principle

**Always prefer MCP tools over native Cline tools for repository operations.**

MCP tools provide:
- Controlled truncation (`MAX_TEXT_CHARS`, `max_chars`, `row_limit`)
- Structured output (JSON, numbered lines)
- Direct Git/SQLite/RAG/broker HTTP integration
- Bounded execution with timeout and max_results

Native Cline tools (`read_file`, `search_files`, `list_files`, `execute_command`) are too generic and lack structured context.

## Tool Priority Table

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read file | `aicarmine_repo_read` | `read_file` |
| Search repo | `aicarmine_repo_search`, `aicarmine_repo_rg_search` | `search_files` |
| List files | `aicarmine_repo_list_files`, `aicarmine_repo_tree` | `list_files` |
| Git operations | `aicarmine_git_readonly_*` | `execute_command git` |
| SQLite queries | `aicarmine_sqlite_readonly_*` | `execute_command sqlite3` |
| Semantic search | `aicarmine_rag_context` | `search_files` + manual read |
| Code validation | `aicarmine_repo_ruff_check`, `pyright_check`, `pytest_run`, `shellcheck`, `semgrep_scan` | `execute_command ruff/pyright/pytest` |

## Workflow Before Modifying Files

1. `aicarmine_repo_read` → read the actual file
2. `aicarmine_git_readonly_diff` → check uncommitted changes
3. `aicarmine_git_readonly_log` → check recent history
4. `aicarmine_repo_status` → verify repository state

## Workflow Before Searching Information

1. `aicarmine_rag_context` → semantic orientation
2. `aicarmine_repo_search` → structured text search
3. `aicarmine_memory_state_packet` → recover operational state

## Essential MCP Servers

| Server | Tools | Purpose |
|--------|-------|---------|
| `aicarmine-codex-app` | 32 tools | Repository operations, jobs, memory, validation |
| `aicarmine-agentic-loop-client` | 7 tools | Agentic task execution (broker HTTP) |
| `aicarmine-local-subagent` | 3 tools | Parallel read-only research |
| `aicarmine-sqlite-readonly` | 3 tools | SQLite queries |
| `aicarmine-rag` | 3 tools | Semantic search |

## Redundant Servers (tools duplicated in codex-app)

- `aicarmine-repo-state`, `aicarmine-repo-search-det`, `aicarmine-repo-code`, `aicarmine-repo-validate`
- `aicarmine-project-memory`, `aicarmine-sqlite-readonly`, `aicarmine-rag`
- `aicarmine-job-artifact`, `aicarmine-job-view`, `aicarmine-codex-ops`, `aicarmine-git-readonly`

## Completion Format

### Symptom
Observed behavior only.

### Evidence
Concrete MCP, source, Git, process, port, log, payload, or database evidence.

### Confirmed cause
The demonstrated causal mechanism only.

### Minimal fix
The smallest contract-preserving change.

### Verification
Original symptom result, targeted checks, resulting diff, and modified source-file line counts.

### Residual risk
Only conditions that remain unverified.