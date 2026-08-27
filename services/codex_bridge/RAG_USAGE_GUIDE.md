# AICarmine Global RAG MCP Server — Usage Guide

## Overview

The **aicarmine-rag-global** MCP server (v2.0.0) provides RAG-based full-text search across any code base under `C:\Users\someo\`. It auto-creates a separate SQLite DB per unique search path, so you can index multiple repositories without conflicts.

**Server name:** `aicarmine-rag`  
**Version:** 2.0.0  
**Transport:** stdio (JSON-RPC)  
**DB root:** `C:\Users\someo\AI\state\codex_rag_global\`

---

## Exposed Tools

| Tool | Description |
|------|-------------|
| `aicarmine_rag_search` | Search the RAG index with FTS5 full-text search |
| `aicarmine_rag_index_status` | Inspect index status and freshness |
| `aicarmine_rag_reindex` | Build or rebuild the RAG index |
| `aicarmine_rag_health` | Health check for the global RAG server |

---

## Quick Start

### 1. Build an Index

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_reindex",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop",
      "source": "filesystem",
      "mode": "full"
    }
  }
}
```

**Response:**
```json
{
  "ok": true,
  "tool": "aicarmine_rag_reindex",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "db": "C:\\Users\\someo\\AI\\state\\codex_rag_global\\rag_ef83a7cd06af9827.sqlite3",
  "result": {
    "files_indexed": 1778,
    "chunks_indexed": 3224
  }
}
```

### 2. Check Index Status

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_index_status",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop"
    }
  }
}
```

**Response fields:**
- `stale`: boolean — true if index is outdated
- `current_commit`: current Git HEAD commit
- `indexed_commit`: commit that was indexed (empty for filesystem mode)
- `db_status.tables`: SQLite tables with row counts

### 3. Search the Index

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_search",
    "arguments": {
      "search_path": "C:\\Users\\someo\\agentic-tool-loop",
      "query": "RAG index building and chunking logic",
      "top_k": 12,
      "candidate_limit": 80,
      "rerank": false
    }
  }
}
```

**Response fields:**
- `chunks`: array of matched chunks with `path`, `content`, `rank`, `fts_rank`
- `candidate_count`: total candidates retrieved before top-k filtering
- `returned`: number of chunks in final response
- `used_chars`: total characters in returned chunks
- `rerank`: reranker status (enabled/disabled/unavailable)
- `warnings`: any warnings during search

### 4. Health Check

```json
{
  "method": "tools/call",
  "params": {
    "name": "aicarmine_rag_health",
    "arguments": {}
  }
}
```

---

## Configuration Options

### aicarmine_rag_search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | **required** | Search query text |
| `search_path` | string | auto-detect | Path to search (must be under C:\Users\someo\) |
| `db` | string | auto-detect | Explicit DB path |
| `candidate_limit` | int | 80 | Max candidates from FTS5 |
| `top_k` | int | 12 | Final chunks returned |
| `max_chunk_chars` | int | 4000 | Max chars per chunk |
| `max_total_chars` | int | 50000 | Total chars in response |
| `rerank` | bool | true | Enable reranking |
| `rerank_candidate_limit` | int | 12 | Candidates for reranker |
| `rerank_doc_chars` | int | 2500 | Max chars per doc for reranker |
| `rerank_timeout_seconds` | float | 30.0 | Reranker timeout |

### aicarmine_rag_reindex Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search_path` | string | **required** | Path to index |
| `source` | enum | "git" | "git" or "filesystem" |
| `mode` | enum | "delta" | "delta" or "full" |
| `suffixes` | string | ".py,.md,.yaml,.yml,.json,.csv,.sql,.txt" | Comma-separated extensions |
| `max_file_bytes` | int | 2000000 | Max file size (2MB) |
| `chunk_lines` | int | 180 | Max lines per chunk |
| `chunk_chars` | int | 12000 | Max chars per chunk |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AICARMINE_RAG_DB_ROOT` | `C:\Users\someo\AI\state\codex_rag_global` | DB storage root |
| `AICARMINE_RAG_REPO` | — | Default search path |
| `AICARMINE_RAG_MCP_STDIO_TRANSPORT` | "jsonl" | "jsonl" or "content-length" |
| `AICARMINE_RAG_MCP_DEBUG` | "0" | Enable debug logging |
| `AICARMINE_RAG_RERANK_URL` | `http://127.0.0.1:3550/v3/rerank` | Reranker endpoint |
| `AICARMINE_RAG_RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Reranker model name |
| `AICARMINE_RAG_RERANK_CANDIDATE_LIMIT` | 12 | Reranker candidate limit |
| `AICARMINE_RAG_RERANK_DOC_CHARS` | 2500 | Max chars per doc |
| `AICARMINE_RAG_RERANK_TIMEOUT_SECONDS` | 30.0 | Reranker timeout |

---

## Path Validation

The server enforces paths under `C:\Users\someo\`. Forbidden prefixes:
- `C:\Windows`
- `C:\Program Files`
- `C:\Users\carmi`
- `C:\ProgramData`

---

## DB Naming

Each unique search path gets a separate SQLite DB named by SHA-256 hash:
```
C:\Users\someo\AI\state\codex_rag_global\rag_<sha256_hash>.sqlite3
```

Example:
- `C:\Users\someo\agentic-tool-loop` → `rag_ef83a7cd06af9827.sqlite3`
- `C:\Users\someo\Z3l07IA` → `rag_82f17b1352f6e168.sqlite3`

---

## Example Queries

### Search for specific code patterns
```json
{
  "query": "def build_chunks",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "top_k": 5
}
```

### Find documentation files
```json
{
  "query": "MCP server configuration tool registration",
  "search_path": "C:\\Users\\someo\\agentic-tool-loop",
  "top_k": 10
}
```

### Search across Z3l07IA code base
```json
{
  "query": "FastAPI main entry point uvicorn",
  "search_path": "C:\\Users\\someo\\Z3l07IA",
  "top_k": 8,
  "rerank": false
}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `db_not_found` error | Run `aicarmine_rag_reindex` first to build the index |
| Reranker unavailable | Set `"rerank": false` or start OVMS reranker on port 3550 |
| Path validation failed | Ensure path is under `C:\Users\someo\` and not a forbidden prefix |
| Empty results | Try broader query terms or increase `candidate_limit` |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Cline / MCP Client                │
└──────────────────┬──────────────────────────────────┘
                   │ stdio (JSON-RPC)
                   ▼
┌─────────────────────────────────────────────────────┐
│           aicarmine-rag-global MCP Server            │
│  ┌─────────────────────────────────────────────────┐│
│  │  aicarmine_rag_search    → FTS5 full-text search││
│  │  aicarmine_rag_reindex   → Build/rebuild index  ││
│  │  aicarmine_rag_index_status → Check freshness   ││
│  │  aicarmine_rag_health    → Server health check  ││
│  └─────────────────────────────────────────────────┘│
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│           SQLite RAG Database (per path)             │
│  ┌─────────────────────────────────────────────────┐│
│  │  chunks          → File content chunks          ││
│  │  chunks_fts      → FTS5 virtual table           ││
│  │  files           → Indexed file metadata        ││
│  │  index_meta      → Index configuration          ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## Version History

| Version | Changes |
|---------|---------|
| 2.0.0 | Global RAG with auto-DB per search path, path validation, filesystem/git source modes |
| 1.x | Legacy single-path RAG |

---

## Related Files

- `services/codex_bridge/rag_mcp_server.py` — Server implementation
- `services/codex_bridge/rag_index_repo.py` — Index building library
- `.vscode/mcp.json` — Workspace MCP config
- `../AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` — Cline global MCP settings