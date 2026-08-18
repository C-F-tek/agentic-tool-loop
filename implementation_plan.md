# Implementation Plan: Sub-Agents System & Embedding DB Derivation

## Overview

This plan covers the implementation of a sub-agents system for distributed task execution and the complete documentation of how the embedding database is derived from the RAG indexer. The sub-agents system will enable parallel task execution across multiple MCP servers, while the embedding DB guide will document the complete pipeline from repository files → RAG chunks → embeddings.

## Types

- **SubAgent**: Represents a distributed agent instance that can execute tasks in parallel
- **EmbeddingPipeline**: Documents the complete flow from repo files to indexed embeddings
- **TaskGraph**: Directed acyclic graph of sub-agent dependencies

```python
class SubAgent:
    id: str
    name: str
    mcp_server: str  # e.g., "aicarmine-rag", "aicarmine-ollama-embedding"
    status: str  # "idle", "running", "error"
    tasks: list[Task]

class EmbeddingPipeline:
    source: str  # "git" or "filesystem"
    mode: str  # "delta" or "full"
    chunks_count: int
    embeddings_count: int
    db_path: str
```

## Files

### New files to be created:
- `services/codex_bridge/sub_agents.py` - Sub-agent orchestration module
- `services/launch/SUB_AGENTS_GUIDE.md` - Complete guide for sub-agents functionality
- `services/launch/EMBEDDING_DB_DERIVATION.md` - Documentation of how embedding DB is derived from RAG indexer

### Existing files to be modified:
- `services/codex_bridge/build_embedding_index.py` - Update to use new sub-agent pattern
- `services/launch/EMBEDDING_AND_RAG_GUIDE.md` - Add cross-reference to new documentation

## Functions

### New functions:
- `create_sub_agent(name: str, mcp_server: str) -> SubAgent` - Create a new sub-agent instance
- `execute_parallel_tasks(tasks: list[Task]) -> dict[str, Result]` - Execute multiple tasks across sub-agents
- `build_embedding_from_rag(rag_db: Path, embedding_db: Path) -> EmbeddingPipeline` - Build embeddings from RAG chunks

### Modified functions:
- `aicarmine_rag_reindex()` - Add sub-agent execution support
- `embedding_search()` - Add parallel query support across sub-agents

## Dependencies

- **New dependencies**: None (uses existing MCP server infrastructure)
- **Version changes**: Python 3.10+ required for async support
- **Integration requirements**: Must work with existing aicarmine-rag, aicarmine-ollama-embedding, and aicarmine-embedding MCP servers

## Testing

- Test sub-agent creation and task execution
- Verify embedding pipeline produces correct 768-dim vectors
- Validate parallel task execution across multiple MCP servers
- Test error handling when individual sub-agents fail

## Implementation Order

1. Create sub_agents.py module with basic orchestration
2. Document embedding DB derivation from RAG indexer
3. Update existing scripts to use new patterns
4. Add comprehensive testing
5. Create complete guide for sub-agents functionality