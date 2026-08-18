# AICarmine Embedding & RAG System Guide

## Overview

This guide covers the complete AICarmine Embedding and RAG (Retrieval-Augmented Generation) system, including:
- **RAG Index**: Code chunks indexed from repository files
- **Embedding Index**: Semantic embeddings generated from RAG chunks via Ollama nomic-embed-text
- **MCP Servers**: aicarmine-rag, aicarmine-ollama-embedding, aicarmine-embedding (OVMS)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    AICarmine RAG + Embedding Stack                  │
├──────────────────────────────────────────────────────────────────┤
│  1. Repository Files (.py, .js, .ts, etc.)                        │
│     └─ git ls-files --cached --others --exclude-standard           │
├──────────────────────────────────────────────────────────────────┤
│  2. RAG Index (code_rag.sqlite3)                                  │
│     ├── chunks table: 3198 rows (path, start_line, end_line,     │
│     │   symbol, kind, content, content_hash)                      │
│     ├── chunks_fts: FTS5 virtual table for full-text search        │
│     └── files table: 1773 indexed files                           │
├──────────────────────────────────────────────────────────────────┤
│  3. Embedding Index (embeddings.sqlite3)                          │
│     ├── embeddings table: 3198 rows (same chunks, with FP32        │
│     │   embeddings generated via Ollama nomic-embed-text)          │
│     ├── embeddings_fts: FTS5 virtual table for semantic search     │
│     └── metadata: JSON-encoded embedding vectors (768-dim)         │
├──────────────────────────────────────────────────────────────────┤
│  4. Ollama Embedding Service (port 11435)                         │
│     ├── Model: nomic-embed-text                                   │
│     ├── API: /api/embed                                           │
│     └── Output: FP32 embeddings, 768-dim                          │
├──────────────────────────────────────────────────────────────────┤
│  5. MCP Servers                                                   │
│     ├── aicarmine-rag: RAG index management, reindex, search      │
│     ├── aicarmine-ollama-embedding: Embedding generation, search   │
│     └── aicarmine-embedding (OVMS): OVMS-based embeddings          │
└──────────────────────────────────────────────────────────────────┘
```

## 1. Database Relationships

### 1.1 RAG DB → Embedding DB Dependency

The embedding database is **derived from** the RAG indexer:

```
Repo Files → RAG Index (chunks) → Embedding Index (embeddings)
```

- **RAG DB**: `C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3`
  - Contains: chunks, chunks_fts, files, index_meta, symbols
  - Source: git ls-files --cached --others --exclude-standard
  - Mode: full reindex = 1773 files, 3198 chunks

- **Embedding DB**: `C:\Users\sanit\AI\state\codex_rag\embeddings.sqlite3`
  - Contains: embeddings, embeddings_fts
  - Source: RAG chunks (SELECT FROM chunks)
  - Embeddings: Generated via Ollama nomic-embed-text API

### 1.2 Schema Comparison

**RAG DB chunks table:**
```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_root TEXT NOT NULL,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol TEXT,
    kind TEXT,
    content TEXT NOT NULL,
    content_hash TEXT,
    updated_at TIMESTAMP
);
```

**Embedding DB embeddings table:**
```sql
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol TEXT,
    kind TEXT,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- JSON-encoded FP32 array (768-dim)
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2. Installation & Setup

### 2.1 Prerequisites

- **Python 3.10+** with virtual environment
- **Ollama** installed with nomic-embed-text model
- **SQLite 3.35+** with FTS5 support enabled
- **Port 11435** available for Ollama embedding service

### 2.2 Verify Ollama Embedding Service

```powershell
# Check if Ollama embedding service is running on port 11435
netstat -ano | findstr ":11435"

# Test Ollama embedding endpoint
curl -s -X POST http://127.0.0.1:11435/api/embed `
  -H "Content-Type: application/json" `
  -d '{"model": "nomic-embed-text", "input": "test"}'
```

### 2.3 Build RAG Index

```powershell
# Reindex repository files
python -u services/codex_bridge/rag_mcp_server.py
# Or via MCP tool call: aicarmine_rag_reindex with mode=full, source=git
```

### 2.4 Build Embedding Index

```powershell
# Build embeddings from RAG chunks
python -u services/codex_bridge/build_embedding_index.py
```

## 3. Usage

### 3.1 Generate Embeddings

```python
# Via MCP tool call (stdio)
{
    "method": "tools/call",
    "params": {
        "name": "ollama_embedding_embed_text",
        "arguments": {
            "text": "Python async programming patterns"
        }
    }
}

# Direct Ollama API call
curl -s -X POST http://127.0.0.1:11435/api/embed `
  -H "Content-Type: application/json" `
  -d '{"model": "nomic-embed-text", "input": "Python async programming patterns"}'
```

### 3.2 Semantic Search

```python
# Via MCP tool call
{
    "method": "tools/call",
    "params": {
        "name": "embedding_search",
        "arguments": {
            "query": "How to use MCP tools?",
            "top_k": 10
        }
    }
}

# Direct SQLite query
python -c "
import sqlite3
conn = sqlite3.connect('C:/Users/sanit/AI/state/codex_rag/embeddings.sqlite3')
cursor = conn.cursor()
cursor.execute('SELECT path, start_line, end_line FROM embeddings_fts WHERE embeddings MATCH ?', ('MCP tools',))
results = cursor.fetchall()
for row in results:
    print(f'{row[0]}:{row[1]}')
conn.close()
"
```

### 3.3 Similarity Computation

```python
# Compute cosine similarity between two embeddings
python -c "
import json
import sqlite3

def cosine_similarity(a, b):
    return sum(x * y for x, y in zip(a, b)) / (
        (sum(x * x for x in a) ** 0.5) * 
        (sum(x * x for x in b) ** 0.5)
    )

conn = sqlite3.connect('C:/Users/sanit/AI/state/codex_rag/embeddings.sqlite3')
cursor = conn.cursor()

# Get embedding for query text
cursor.execute('SELECT embedding FROM embeddings WHERE path = ?', ('services/codex_bridge/ollama_embedding_mcp_server.py',))
query_emb = json.loads(cursor.fetchone()[0])

# Compare with all other embeddings
cursor.execute('SELECT path, embedding FROM embeddings')
similarities = []
for path, emb_bytes in cursor.fetchall():
    emb = json.loads(emb_bytes)
    sim = cosine_similarity(query_emb, emb)
    similarities.append((path, sim))

# Sort by similarity
similarities.sort(key=lambda x: x[1], reverse=True)
for path, sim in similarities[:5]:
    print(f'{path}: {sim:.4f}')
conn.close()
"
```

## 4. Troubleshooting

### 4.1 Ollama Service Not Responding

**Symptom**: `ollama_ready: false`

**Evidence**: Port 11435 not listening, or HTTP 500 responses

**Fix**:
```powershell
# Check if Ollama process is running
Get-Process -Name "ollama" -ErrorAction SilentlyContinue

# Start Ollama embedding service
ollama pull nomic-embed-text

# Verify port binding
netstat -ano | findstr ":11435"
```

### 4.2 Empty Search Results

**Symptom**: `embedding_search` returns empty results

**Evidence**: No embeddings indexed in SQLite DB

**Fix**:
```powershell
# Check if files are indexed
sqlite3 "C:/Users/sanit/AI/state/codex_rag/embeddings.sqlite3" "SELECT COUNT(*) FROM embeddings;"

# Rebuild index if empty
python -u services/codex_bridge/build_embedding_index.py
```

### 4.3 RAG Index Returns 0 Files

**Symptom**: `aicarmine_rag_reindex` returns `candidate_files: 0`

**Evidence**: Git source returns no candidates, or filesystem source filters by suffix

**Fix**:
1. Verify `.gitignore` is not excluding all files
2. Use `source='filesystem'` instead of `source='git'`
3. Check that file suffixes match expected patterns (e.g., `.py` not `.pyi`)

## 5. MCP Tool Reference

### 5.1 Available Tools

| Tool | Description | Input Schema |
|------|-------------|--------------|
| `aicarmine_rag_reindex` | Rebuild RAG index from repository | `{"repo": string, "mode": enum[delta,full], "source": enum[git,filesystem]}` |
| `aicarmine_rag_context` | Search RAG index for context | `{"query": string, "top_k": int, "rerank": bool}` |
| `ollama_embedding_health` | Check Ollama embedding service health | `{}` |
| `ollama_embedding_embed_text` | Generate embedding for single text | `{"text": string}` |
| `ollama_embedding_embed_batch` | Generate embeddings for multiple texts | `{"texts": [string]}` |
| `embedding_search` | Search embeddings by similarity | `{"query": string, "top_k": int}` |
| `embedding_similarity` | Compute similarity between two texts | `{"text1": string, "text2": string}` |

### 5.2 Tool Call Format

```json
{
    "method": "tools/call",
    "params": {
        "name": "ollama_embedding_embed_text",
        "arguments": {
            "text": "Python async programming patterns"
        }
    }
}
```

## 6. Integration with RAG System

### 6.1 RAG Index → Embedding Flow

```
Repo Files → RAG Index (chunks) → Ollama Embeddings → SQLite DB → Semantic Search
```

### 6.2 End-to-End Example

```python
# 1. Index repo files
aicarmine_rag_reindex(repo_root="C:/Users/sanit/agentic-tool-loop", mode="full", source="git")

# 2. Build embeddings from RAG chunks
python -u services/codex_bridge/build_embedding_index.py

# 3. Generate embedding for query
embedding = ollama_embedding_embed_text(text="How to use MCP tools?")

# 4. Search indexed chunks
results = embedding_search(query="How to use MCP tools?", top_k=10)

# 5. Compute similarity
similarity = embedding_similarity(text1="MCP tool usage", text2="How to use MCP tools?")
```

## 7. Maintenance

### 7.1 Rebuild Index

```powershell
# Delete existing DBs and rebuild
Remove-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" -Force
Remove-Item "C:\Users\sanit\AI\state\codex_rag\embeddings.sqlite3" -Force

# Rebuild RAG index
python -c "from services.codex_bridge.rag_mcp_server import build_index; ..."

# Rebuild embedding index
python -u services/codex_bridge/build_embedding_index.py
```

### 7.2 Monitor Health

```powershell
# Check Ollama embedding service health
curl -s -X POST http://127.0.0.1:11435/api/embed `
  -H "Content-Type: application/json" `
  -d '{"model": "nomic-embed-text", "input": ""}'

# Check SQLite DB size
ls "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3"
ls "C:\Users\sanit\AI\state\codex_rag\embeddings.sqlite3"
```

### 7.3 Backup

```powershell
# Backup SQLite DBs
Copy-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" "C:\Users\sanit\AI\state\codex_rag\code_rag.backup.sqlite3"
Copy-Item "C:\Users\sanit\AI\state\codex_rag\embeddings.sqlite3" "C:\Users\sanit\AI\state\codex_rag\embeddings.backup.sqlite3"
```

## 8. Known Issues

1. **Ollama timeout**: Large embedding batches may timeout the MCP stdio protocol. Use smaller batch sizes or individual text embeddings.

2. **FTS5 tokenization**: The FTS5 virtual table may not handle all Unicode characters correctly. Test with representative data.

3. **Git source returns 0 files**: The `.gitignore` file may exclude all repository files from indexing. Use `source='filesystem'` as a workaround.

## 9. References

- [RAG Index Repository](../services/codex_bridge/rag_index_repo.py)
- [Embedding MCP Server](../services/codex_bridge/ollama_embedding_mcp_server.py)
- [Build Embedding Index Script](../services/codex_bridge/build_embedding_index.py)
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)