# AICarmine Intelligent Search Flow: Reranker + Embedding

## Overview

This guide covers the correct logical flow for intelligent search using both **embedding** (semantic similarity) and **reranker** (relevance scoring) in the AICarmine system.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   AICarmine Intelligent Search Stack               │
├──────────────────────────────────────────────────────────────────┤
│  1. User Query                                                      │
│     └─ "How to use MCP tools?"                                    │
├──────────────────────────────────────────────────────────────────┤
│  2. Embedding Service (Ollama nomic-embed-text, port 11435)      │
│     ├── Generate embedding for query                               │
│     └─ Compare with all chunk embeddings                        │
├──────────────────────────────────────────────────────────────────┤
│  3. RAG Index (code_rag.sqlite3)                                  │
│     ├── chunks table: 3198 rows                                  │
│     └── chunks_fts: FTS5 virtual table                           │
├──────────────────────────────────────────────────────────────────┤
│  4. Candidate Selection (top-K chunks by similarity)              │
│     └─ Return top 10-20 most similar chunks                       │
├──────────────────────────────────────────────────────────────────┤
│  5. Reranker Service (OVMS BAAI/bge-reranker-v2-m3, port 3550)   │
│     ├── Score each candidate chunk against query                  │
│     └─ Return ranked results by relevance score                   │
├──────────────────────────────────────────────────────────────────┤
│  6. Final Results                                                 │
│     └─ Top-N chunks ordered by relevance                         │
└──────────────────────────────────────────────────────────────────┘
```

## 1. Correct Logical Flow

### 1.1 Step-by-Step Sequence

```
Query → Embedding → Candidate Selection → Reranking → Final Results
```

### 1.2 Detailed Steps

1. **Query Generation**: User provides natural language query
   ```
   "How to use MCP tools?"
   ```

2. **Embedding Generation**: Convert query to 768-dim vector using Ollama nomic-embed-text
   ```python
   # Via Ollama API
   curl -s -X POST http://127.0.0.1:11435/api/embed \
     -H "Content-Type: application/json" \
     -d '{"model": "nomic-embed-text", "input": "How to use MCP tools?"}'
   ```

3. **Candidate Selection**: Search RAG index for top-K most similar chunks
   ```python
   # Via aicarmine-rag MCP server
   {
       "method": "tools/call",
       "params": {
           "name": "aicarmine_rag_context",
           "arguments": {
               "query": "How to use MCP tools?",
               "top_k": 20,
               "rerank": false
           }
       }
   }
   ```

4. **Reranking**: Score each candidate chunk against the query using OVMS reranker
   ```python
   # Via OVMS API
   curl -s -X POST http://127.0.0.1:3550/v3/rerank \
     -H "Content-Type: application/json" \
     -d '{"model": "BAAI/bge-reranker-v2-m3", "query": "How to use MCP tools?", "documents": [...], "top_n": 10}'
   ```

5. **Final Results**: Return top-N chunks ordered by relevance score
   ```python
   # Final ranked results
   [
       {"chunk_id": 1234, "path": "services/codex_bridge/rag_mcp_server.py", "score": 0.95},
       {"chunk_id": 5678, "path": "services/codex_bridge/ollama_embedding_mcp_server.py", "score": 0.87},
       ...
   ]
   ```

## 2. MCP Tool Calls for Each Step

### 2.1 aicarmine-rag Server

| Tool | Purpose | Input Schema |
|------|---------|--------------|
| `aicarmine_rag_reindex` | Rebuild RAG index from repository | `{"repo": string, "mode": enum[delta,full], "source": enum[git,filesystem]}` |
| `aicarmine_rag_context` | Search RAG index for context | `{"query": string, "top_k": int, "rerank": bool}` |

### 2.2 aicarmine-ollama-embedding Server

| Tool | Purpose | Input Schema |
|------|---------|--------------|
| `ollama_embedding_health` | Check Ollama embedding service health | `{}` |
| `ollama_embedding_embed_text` | Generate embedding for single text | `{"text": string}` |
| `embedding_search` | Search embeddings by similarity | `{"query": string, "top_k": int}` |

### 2.3 OVMS Reranker Service

| Endpoint | Purpose | Input Schema |
|----------|---------|--------------|
| `/v2/models/BAAI/bge-reranker-v2-m3/ready` | Health check | `{}` |
| `/v3/rerank` | Score documents against query | `{"model": string, "query": string, "documents": [string], "top_n": int}` |

## 3. End-to-End Example

### 3.1 Via MCP Tool Calls

```python
# Step 1: Search RAG index for candidates (without reranking)
aicarmine_rag_context(query="How to use MCP tools?", top_k=20, rerank=false)

# Step 2: Rerank candidates using OVMS reranker
ovms_rerank(query="How to use MCP tools?", documents=[...], top_n=10)

# Step 3: Return final results
[
    {"chunk_id": 1234, "path": "services/codex_bridge/rag_mcp_server.py", "score": 0.95},
    {"chunk_id": 5678, "path": "services/codex_bridge/ollama_embedding_mcp_server.py", "score": 0.87}
]
```

### 3.2 Via Direct API Calls

```python
# Step 1: Generate query embedding
curl -s -X POST http://127.0.0.1:11435/api/embed \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "input": "How to use MCP tools?"}'

# Step 2: Search RAG index for top-K chunks
curl -s -X POST http://127.0.0.1:3550/v2/models/BAAI/bge-reranker-v2-m3/infer \
  -H "Content-Type: application/json" \
  -d '{"model_name": "BAAI/bge-reranker-v2-m3", "query": "How to use MCP tools?", "documents": [...], "top_n": 10}'

# Step 3: Rerank candidates
curl -s -X POST http://127.0.0.1:3550/v3/rerank \
  -H "Content-Type: application/json" \
  -d '{"model": "BAAI/bge-reranker-v2-m3", "query": "How to use MCP tools?", "documents": [...], "top_n": 10}'
```

## 4. Troubleshooting

### 4.1 Reranker Service Not Responding

**Symptom**: `ovms_ready: false`

**Evidence**: Port 3550 not listening, or HTTP 500 responses

**Fix**:
```powershell
# Check if OVMS reranker process is running
Get-Process -Name "ovms*" -ErrorAction SilentlyContinue

# Start OVMS reranker service
.venv\Scripts\python.exe services/launch/ovms-reranker-npu.ps1

# Verify port binding
netstat -ano | findstr ":3550"
```

### 4.2 Empty Search Results

**Symptom**: `aicarmine_rag_context` returns empty results

**Evidence**: No chunks indexed in RAG DB

**Fix**:
```powershell
# Check if files are indexed
sqlite3 "C:/Users/sanit/AI/state/codex_rag/code_rag.sqlite3" "SELECT COUNT(*) FROM chunks;"

# Rebuild index if empty
python -u services/codex_bridge/rag_mcp_server.py
```

### 4.3 Reranking Returns Low Scores

**Symptom**: All reranking scores are < 0.5

**Evidence**: Candidates are not relevant to query

**Fix**:
1. Verify that the query matches the candidate content
2. Check that the reranker model is properly loaded
3. Ensure that the documents are properly formatted

## 5. Maintenance

### 5.1 Rebuild Index

```powershell
# Delete existing DBs and rebuild
Remove-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" -Force

# Rebuild RAG index
python -c "from services.codex_bridge.rag_mcp_server import build_index; ..."
```

### 5.2 Monitor Health

```powershell
# Check OVMS reranker service health
curl -s -X POST http://127.0.0.1:3550/v2/models/BAAI/bge-reranker-v2-m3/ready

# Check SQLite DB size
ls "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3"
```

### 5.3 Backup

```powershell
# Backup SQLite DBs
Copy-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" "C:\Users\sanit\AI\state\codex_rag\code_rag.backup.sqlite3"
```

## 6. Known Issues

1. **Reranker timeout**: Large document batches may timeout the OVMS reranker. Use smaller batch sizes or individual document scoring.

2. **Embedding dimension mismatch**: Ensure that the embedding model output dimension matches the reranker input dimension. Ollama nomic-embed-text outputs 768-dim vectors, while OVMS reranker expects 384-dim vectors (from MiniLM-L6-v2).

3. **FTS5 tokenization**: The FTS5 virtual table may not handle all Unicode characters correctly. Test with representative data.

## 7. References

- [RAG Index Repository](../services/codex_bridge/rag_index_repo.py)
- [Embedding MCP Server](../services/codex_bridge/ollama_embedding_mcp_server.py)
- [OVMS Reranker Service Guide](./OVMS_RERANKER_SERVER_GUIDE.md)
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)