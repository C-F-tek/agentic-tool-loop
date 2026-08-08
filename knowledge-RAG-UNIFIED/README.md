# Knowledge RAG Unified - Star Schema

## Architettura

Questo progetto implementa una "star schema" per i RAG DB, con un DB centrale che indicizza tutti i metadati e sommari dei RAG DB esistenti.

## RAG DB Esistenti

| DB | Path | Files | Chunks |
|----|------|-------|--------|
| knowledge-OVMS | knowledge-OVMS/rag_ovms.db | 19 | 203 |
| knowledge-OLLAMA-full | knowledge-OLLAMA-full/rag_ollama_full.db | 71 | 286 |
| knowledge-OPENWEBUI-full | knowledge-OPENWEBUI-full/rag_openwebui_full.db | 337 | 3338 |
| knowledge-AI-SECURITY | knowledge-AI-SECURITY/rag_ai_security.db | 2012 | 4792 |

## RAG DB Unificato

| DB | Path | Files | Chunks |
|----|------|-------|--------|
| knowledge-RAG-UNIFIED | knowledge-RAG-UNIFIED/rag_unified.db | ? | ? |

## Query Multi-DB

```python
# Query unificata su tutti i RAG DB
async def unified_search(query, top_k=10):
    results = []
    dbs = [
        ("OVMS", "knowledge-OVMS/rag_ovms.db"),
        ("OLLAMA", "knowledge-OLLAMA-full/rag_ollama_full.db"),
        ("OPENWEBUI", "knowledge-OPENWEBUI-full/rag_openwebui_full.db"),
        ("AI-SECURITY", "knowledge-AI-SECURITY/rag_ai_security.db")
    ]
    for name, db_path in dbs:
        r = aicarmine_rag_context(query=query, db=db_path, top_k=top_k // 4)
        results.extend(r)
    return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]