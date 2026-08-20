# Agentic Loop - Data Query Agent

This directory contains a specialized agentic loop focused on data querying through an agent that uses RAG as its primary tool.

## Architecture

The agent is the primary component. RAG (Retrieval-Augmented Generation) is one of several tools the agent uses to answer questions about data databases.

## Structure

```
agentic_loop_logc_app/
├── README.md              # This file
├── AGENTS.md              # Agent configuration and contracts
├── config/
│   ├── settings.yaml      # Agent and database configuration
│   └── rag_index.conf     # RAG index parameters
├── agents/
│   ├── __init__.py
│   ├── rag_agent.py       # Main agent implementation (uses RAG as tool)
│   └── data_query.py      # CLI entry point for the agent
├── rag/                     # RAG components (tools used by the agent)
│   ├── __init__.py
│   ├── indexer.py         # Index building tool
│   ├── retriever.py       # Retrieval tool
│   └── reranker.py        # Reranking tool
├── data/
│   ├── __init__.py
│   ├── connectors.py      # Database connectors
│   └── schemas.py         # Schema definitions
├── mcp/
│   ├── __init__.py
│   ├── server.py          # MCP server for agent tools
│   └── tools.py           # Tool definitions
├── tests/
│   ├── __init__.py
│   ├── test_indexer.py
│   ├── test_retriever.py
│   ├── test_reranker.py
│   ├── test_connectors.py
│   ├── test_schemas.py
│   ├── test_rag_agent.py
│   └── test_mcp_server.py
├── logs/                   # Agentic loop logs
└── state/                   # Persistent state (RAG DB, etc.)
```

## First Objective

Create a data query agent that uses RAG to answer questions on a SQLite database.

## Usage

1. Configure database connection in config/settings.yaml
2. Build RAG index using the agent: `python agents/data_query.py --action build`
3. Query using the agent: `python agents/data_query.py --action query --question "your question"`
4. Review logs in logs/ directory