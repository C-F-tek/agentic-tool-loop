test# AICarmine Embedding MCP Server Guide

## Overview

This guide covers the complete installation, configuration, and usage of the AICarmine Embedding MCP Server for semantic search and RAG (Retrieval-Augmented Generation) workflows.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AICarmine Embedding Stack                   │
├─────────────────────────────────────────────────────────────┤
│  1. OVMS Embedding Service (port 3551)                       │
│     - OpenVINO Model Server                                  │
│     - Sentence-transformers model                            │
│     - API: /v2/models/<name>/infer                           │
├─────────────────────────────────────────────────────────────┤
│  2. Embedding MCP Server (stdio)                             │
│     - MCP tool calls via stdio                               │
│     - Tools: ovms_embedding_health, ovms_embedding_embed_text │
│     - Tools: embedding_search, embedding_similarity          │
├─────────────────────────────────────────────────────────────┤
│  3. SQLite RAG DB (code_rag.sqlite3)                         │
│     - embeddings table + FTS5 virtual table                  │
│     - Indexed repo files with chunks                         │
│     - Semantic search via FTS5                               │
└─────────────────────────────────────────────────────────────┘
```

## 1. Installation

### 1.1 Prerequisites

- **Python 3.10+** with virtual environment
- **OpenVINO Model Server (OVMS)** installed and accessible
- **SQLite 3.35+** with FTS5 support enabled
- **Port 3551** available for OVMS embedding service

### 1.2 Clone Repository

```powershell
git clone https://github.com/C-F-tek/agentic-tool-loop.git
cd agentic-tool-loop
```

### 1.3 Install Dependencies

```powershell
# Activate virtual environment
.\activate-venv.ps1

# Install if needed
pip install -r services\requirements-agentic-optional.txt
```

### 1.4 Verify OVMS Embedding Service

```powershell
# Check if OVMS embedding service is running on port 3551
netstat -ano | findstr ":3551"

# Test OVMS endpoint
curl -s -X POST http://127.0.0.1:3551/get `
  -H "Content-Type: application/json" `
  -d '{"model_name": "BAAI/bge-small-en-v1.5", "texts": ["test"]}'
```

## 2. Configuration

### 2.1 Environment Variables

```powershell
# Set environment variables for the embedding system
$env:AICARMINE_RAG_DB = "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3"
$env:AICARMINE_RAG_REPO = "C:\Users\sanit\agentic-tool-loop"
$env:AICARMINE_EMBEDDING_MCP_DEBUG = "1"  # Enable debug logging
```

### 2.2 OVMS Model Configuration

The OVMS embedding service uses:
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Input tensor**: `input_ids` (shape: [batch, seq_len])
- **Output tensor**: `last_hidden_state` (shape: [batch, seq_len, dim])
- **Embedding dimension**: 384 (for MiniLM-L6-v2)

### 2.3 SQLite DB Schema

```sql
-- Main embeddings table
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol TEXT,
    kind TEXT,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- JSON-encoded float array
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table for semantic search
CREATE VIRTUAL TABLE embeddings_fts USING fts5(
    path,
    symbol,
    kind,
    content,
    content='embeddings',
    content_rowid='id',
    tokenize='unicode61'
);
```

## 3. Usage

### 3.1 Generate Embeddings

```python
# Via MCP tool call (stdio)
{
    "method": "tools/call",
    "params": {
        "name": "ovms_embedding_embed_text",
        "arguments": {
            "text": "Python async programming patterns"
        }
    }
}

# Direct API call
curl -s -X POST http://127.0.0.1:3551/get `
  -H "Content-Type: application/json" `
  -d '{"model_name": "BAAI/bge-small-en-v1.5", "texts": ["Python async programming patterns"]}'
```

### 3.2 Index Repository Files

```python
# Build RAG index from repository
python -c "
from services.codex_bridge.rag_index_repo import build_index
from pathlib import Path

result = build_index(
    repo_root=Path('C:/Users/sanit/agentic-tool-loop'),
    db=Path('C:/Users/sanit/AI/state/codex_rag/code_rag.sqlite3'),
    suffixes={'py', 'js', 'ts', 'go', 'rs', 'md'},
    source='filesystem',
    mode='full'
)
print(result)
"
```

### 3.3 Semantic Search

```python
# Search indexed embeddings
python -c "
import sqlite3
from pathlib import Path

conn = sqlite3.connect('C:/Users/sanit/AI/state/codex_rag/code_rag.sqlite3')
cursor = conn.cursor()

# FTS5 search
cursor.execute(
    'SELECT path, start_line, end_line, symbol FROM chunks_fts WHERE chunks MATCH ? ORDER BY rank',
    ('async programming patterns',)
)
results = cursor.fetchall()
for row in results:
    print(f'{row[0]}:{row[1]} - {row[3]}')
"
```

### 3.4 Similarity Computation

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

conn = sqlite3.connect('C:/Users/sanit/AI/state/codex_rag/code_rag.sqlite3')
cursor = conn.cursor()

# Get embedding for query text
cursor.execute('SELECT embedding FROM embeddings WHERE path = ?', ('services/codex_bridge/rag_mcp_server.py',))
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
"
```

## 4. Troubleshooting

### 4.1 OVMS Service Not Responding

**Symptom**: `ovms_ready: false`

**Evidence**: Port 3551 not listening, or HTTP 500 responses

**Fix**:
```powershell
# Check if OVMS process is running
Get-Process -Name "ovms*" -ErrorAction SilentlyContinue

# Start OVMS embedding service
.venv\Scripts\python.exe services/launch/ovms-embed.ps1

# Verify port binding
netstat -ano | findstr ":3551"
```

### 4.2 Placeholder BYTES Output

**Symptom**: API returns HTTP 200 but output is placeholder BYTES instead of FP32 embeddings

**Evidence**: `test_ovms_embed_v11.py` confirms API format works but produces placeholder data

**Fix**:
1. Verify model weights are properly loaded in OVMS
2. Check that the model directory contains valid OpenVINO XML/ONNX files
3. Ensure the input tensor name matches (`input_ids` vs `Parameter_10391`)

### 4.3 Empty Search Results

**Symptom**: `embedding_search` returns empty results

**Evidence**: No embeddings indexed in SQLite DB

**Fix**:
```powershell
# Check if files are indexed
sqlite3 "C:/Users/sanit/AI/state/codex_rag/code_rag.sqlite3" "SELECT COUNT(*) FROM chunks;"

# Reindex if empty
python -c "from services.codex_bridge.rag_index_repo import build_index; ..."
```

### 4.4 Build Index Returns 0 Files

**Symptom**: `build_index` returns `candidate_files: 0`

**Evidence**: Git source returns no candidates, or filesystem source filters by suffix

**Fix**:
1. Verify `.gitignore` is not excluding all files
2. Use `source='filesystem'` instead of `source='git'`
3. Check that file suffixes match expected patterns (e.g., `.py` not `.pyi`)

## 5. MCP Tool Reference

### 5.1 Available Tools

| Tool | Description | Input Schema |
|------|-------------|--------------|
| `ovms_embedding_health` | Check OVMS embedding service health | `{}` |
| `ovms_embedding_list_models` | List available models in OVMS | `{}` |
| `ovms_embedding_embed_text` | Generate embedding for single text | `{"text": string}` |
| `ovms_embedding_embed_batch` | Generate embeddings for multiple texts | `{"texts": [string]}` |
| `embedding_search` | Search embeddings by similarity | `{"query": string, "top_k": int}` |
| `embedding_similarity` | Compute similarity between two texts | `{"text1": string, "text2": string}` |
| `embedding_mcp_health` | Check embedding MCP server health | `{}` |

### 5.2 Tool Call Format

```json
{
    "method": "tools/call",
    "params": {
        "name": "ovms_embedding_embed_text",
        "arguments": {
            "text": "Python async programming patterns"
        }
    }
}
```

## 6. Integration with RAG System

### 6.1 RAG Index → Embedding Flow

```
Repo Files → FTS5 Index → Chunks → OVMS Embeddings → SQLite DB → Semantic Search
```

### 6.2 End-to-End Example

```python
# 1. Index repo files
build_index(repo_root=Path('.'), db=Path('...'), source='filesystem', mode='full')

# 2. Generate embedding for query
embedding = ovms_embedding_embed_text(text="How to use MCP tools?")

# 3. Search indexed chunks
results = embedding_search(query="How to use MCP tools?", top_k=10)

# 4. Compute similarity
similarity = embedding_similarity(text1="MCP tool usage", text2="How to use MCP tools?")
```

## 7. Maintenance

### 7.1 Rebuild Index

```powershell
# Delete existing DB and rebuild
Remove-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" -Force
python -c "from services.codex_bridge.create_embedding_db import create_db; create_db()"
python -c "from services.codex_bridge.rag_index_repo import build_index; ..."
```

### 7.2 Monitor Health

```powershell
# Check OVMS embedding service health
curl -s -X POST http://127.0.0.1:3551/get `
  -H "Content-Type: application/json" `
  -d '{"model_name": "BAAI/bge-small-en-v1.5", "texts": [""]}'

# Check SQLite DB size
ls "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3"
```

### 7.3 Backup

```powershell
# Backup SQLite DB
Copy-Item "C:\Users\sanit\AI\state\codex_rag\code_rag.sqlite3" "C:\Users\sanit\AI\state\codex_rag\code_rag.backup.sqlite3"
```

## 8. Known Issues

1. **OVMS placeholder BYTES**: The OVMS embedding service may return placeholder BYTES instead of real FP32 embeddings if model weights are not properly loaded.

2. **Git source returns 0 files**: The `.gitignore` file may exclude all repository files from indexing. Use `source='filesystem'` as a workaround.

3. **FTS5 tokenization**: The `unicode61` tokenizer may not handle all Unicode characters correctly. Test with representative data.

## 9. References

- [OVMS Embedding Service Guide](./OVMS_EMBEDDING_IMPLEMENTATION_GUIDE.md)
- [RAG Index Repository](../services/codex_bridge/rag_index_repo.py)
- [Embedding MCP Server](../services/codex_bridge/embedding_mcp_server.py)
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)