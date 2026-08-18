# Agentic Loop LogC App - RAG Data Query Agent

## Overview

`agentic_loop_logc_app` is a specialized agentic loop focused on Retrieval-Augmented Generation (RAG) for data querying. It connects to databases, builds RAG indexes from schema and sample data, and answers natural language questions about the data.

## Architecture

```
agentic_loop_logc_app/
├── config/          # Configuration files
├── agents/          # Agent implementations  
├── rag/             # RAG components (indexer, retriever, reranker)
├── data/            # Database connectors and schemas
├── mcp/             # MCP server and tools
├── logs/            # Agentic loop logs
└── state/           # Persistent state (RAG DB, etc.)
```

## Components

### RAG Pipeline

1. **Indexer** (`rag/indexer.py`) - Scans database schema and sample data to build vector index
2. **Retriever** (`rag/retriever.py`) - Retrieves relevant chunks from the index using embedding similarity
3. **Reranker** (`rag/reranker.py`) - Ranks retrieved candidates for relevance

### Data Connectors

- SQLite support via standard library
- PostgreSQL support via `psycopg2` or `asyncpg`  
- CSV file support via `pandas` or `csv` module

## Usage

1. Configure database connection in `config/settings.yaml`
2. Build RAG index using the indexer component
3. Query using the data_query agent with natural language questions
4. Review structured results with citations from source data

## Configuration

- Database: `config/settings.yaml`
- RAG parameters: `config/rag_index.conf`  
- MCP server port: auto-assigned or 3580

## Logging

All agentic loop activity is written to `agentic_loop_logc_app/logs/`.