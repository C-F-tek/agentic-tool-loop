"""
MCP Tools - Tool definitions for the Data RAG Agent MCP server.

This module defines the MCP tools for RAG-based data querying.
"""

from __future__ import annotations

TOOL_SCHEMAS = [
    {
        "name": "aicarmine_data_rag_query",
        "description": "Query the RAG index with a natural language question about the data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "top_k": {"type": "integer", "default": 12},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "aicarmine_data_rag_build_index",
        "description": "Build or rebuild the RAG index from the data source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "default": "."},
                "source_type": {"type": "string", "enum": ["filesystem", "git"], "default": "filesystem"},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "aicarmine_data_rag_index_status",
        "description": "Check the status of the RAG index.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
    },
]

TOOL_HANDLERS = {
    "aicarmine_data_rag_query": "query",
    "aicarmine_data_rag_build_index": "build_index",
    "aicarmine_data_rag_index_status": "index_status",
}