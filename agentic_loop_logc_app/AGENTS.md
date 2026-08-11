# Agentic Loop - Data RAG Agent Rules

This directory contains a specialized agentic loop focused on RAG-based data querying.

## Purpose

Build an agent that uses RAG (Retrieval-Augmented Generation) to answer questions on a data database.

## Structure

```
agentic_loop_logc_app/
├── config/          # Configuration files
├── agents/          # Agent implementations
├── rag/             # RAG components (indexer, retriever, reranker)
├── data/            # Database connectors and schemas
├── mcp/             # MCP server and tools
├── logs/            # Agentic loop logs
└── state/            # Persistent state (RAG DB, etc.)
```

## Operating Principles

1. RAG index must be built before querying
2. Database connectors must support SQLite, PostgreSQL, and CSV
3. MCP tools must follow the aicarmine_ prefix convention
4. All queries must be read-only unless explicitly authorized
5. Logs must be written to agentic_loop_logc_app/logs/

## First Objective

Create a data query agent that:
- Connects to a SQLite database
- Builds a RAG index from the database schema and sample data
- Answers natural language questions about the data
- Returns structured results with citations

## Configuration

- Database connection: config/settings.yaml
- RAG parameters: config/rag_index.conf
- MCP server port: auto-assigned or 3580

## Usage

1. Configure database connection in config/settings.yaml
2. Build RAG index using the indexer
3. Query using the data_query agent
4. Review logs in logs/ directory