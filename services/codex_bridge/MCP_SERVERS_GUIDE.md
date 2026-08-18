# Codex Bridge MCP Servers Guide

## Overview

The `codex_bridge/` package implements multiple MCP (Model Context Protocol) servers for the AICarmine system. Each server provides a specific set of capabilities through stdio JSON-RPC communication.

## Architecture

```
codex_bridge/
├── mcp_server.py              # Main Codex MCP JSON-RPC server
├── repo_mcp_common.py         # Shared helpers for deterministic repo MCP servers
├── repo_state_mcp_server.py   # Repo state, status and capability tools
├── repo_search_det_mcp_server.py  # Deterministic local repo search
├── repo_validate_mcp_server.py    # Validation tools (read-only)
├── repo_code_mcp_server.py      # Candidate code edit tools (incubating)
├── ops_mcp_server.py          # Operational checks (non-agentic)
├── sqlite_readonly_mcp_server.py  # Read-only SQLite diagnostics
├── job_artifact_mcp_server.py   # Persisted agent job artifacts
├── job_view_mcp_server.py     # Persisted agent job HTML views
├── git_readonly_mcp_server.py # Read-only Git regression diagnostics
├── project_memory_mcp_server.py  # Project-local persistent memory
├── local_subagent_mcp_server.py   # Local subagent facade (3579)
├── rag_index_repo.py        # Standalone RAG index builder
├── rag_mcp_server.py        # Dedicated Codex RAG MCP stdio server
├── embedding_mcp_server.py  # OVMS embedding generation
├── ollama_embedding_mcp_server.py # Ollama embedding generation
├── intelligent_search.py    # Complete search pipeline (query→embed→rerank)
├── intelligent_search_mcp_server.py # Intelligent search MCP server
└── unified_reindex_mcp_server.py  # Atomic reindex proxy
```

## Server Inventory

### Core Servers

| Server | Port/Transport | Purpose | Read-Only |
|--------|---------------|---------|-----------|
| `aicarmine-codex-app` | stdio | Main Codex MCP server | No (selective writes) |
| `aicarmine-repo-state` | stdio | Repo state, status, capabilities | Yes |
| `aicarmine-repo-search-det` | stdio | Deterministic search (fd, rg, ast-grep) | Yes |
| `aicarmine-repo-validate` | stdio | Validation tools (diffcheck, ruff, pyright) | No (validation only) |
| `aicarmine-repo-code` | stdio | Candidate code edit proposals | No (write with guard) |

### Diagnostic Servers

| Server | Port/Transport | Purpose | Read-Only |
|--------|---------------|---------|-----------|
| `aicarmine-ops` | stdio | Operational checks, ports, processes, logs | Yes |
| `aicarmine-sqlite-readonly` | stdio | Allowlisted SQLite queries | Yes |
| `aicarmine-job-artifact` | stdio | Persisted agent job artifacts | Yes |
| `aicarmine-job-view` | stdio | Persisted agent HTML views | Yes |
| `aicarmine-git-readonly` | stdio | Git log, show, diff, blame | Yes |

### Memory & Search Servers

| Server | Port/Transport | Purpose | Read-Only |
|--------|---------------|---------|-----------|
| `aicarmine-project-memory` | stdio | Project-local persistent memory | No (write with confirmation) |
| `aicarmine-rag` | stdio | RAG context, index status, reindex | No (reindex writes) |
| `aicarmine-intelligent-search` | stdio | Complete search pipeline | Yes |

### Embedding Servers

| Server | Port/Transport | Purpose | Read-Only |
|--------|---------------|---------|-----------|
| `aicarmine-embedding` | stdio | OVMS embedding generation | No (writes to SQLite) |
| `aicarmine-ollama-embedding` | stdio | Ollama embedding generation | Yes |

## Key Protocols

### Codex Root Selection

Each MCP process selects its own repo root via `AICARMINE_CODEX_MCP_REPO_ROOT`. The `repo_mcp_common.py` synchronizes this before any broker-tool imports. Do not inherit from OpenWebUI/3572 lab shadow.

### Write Guards

- **Read-only servers** (state, search, sqlite, job-artifact, git): Never write source files
- **Validation server**: Only runs validation commands; does not edit project source
- **Code proposal server**: Writes only audit JSON under `tool-results/`; never applies changes
- **Project memory**: Requires explicit confirmation strings for upsert/supersede/marking stale

### No Agentic Loop

None of the MCP servers implement or call the agentic loop. They are tool surfaces, not decision loops. The broker planner/controller/validator path remains the enforcement boundary.

## Verification

- Check `*_health` endpoints return expected capabilities
- Verify read-only servers cannot write source files
- Confirm code proposal server only writes audit JSON
- Test that project memory requires confirmation strings for writes