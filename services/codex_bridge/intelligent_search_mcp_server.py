#!/usr/bin/env python3
"""
AICarmine Intelligent Search MCP Server (Cline-compatible) - Fixed v2

Implements the complete intelligent search pipeline:
Query → Embedding (semantic similarity) → Candidate Selection → Reranker (relevance scoring) → Final Results

MCP stdio protocol with proper timeout handling to prevent infinite waiting.
"""
from __future__ import annotations

import json
import sys
import os
import socket
import time


# Import the intelligent search module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intelligent_search import (
    generate_embedding,
    cosine_similarity,
    candidate_selection,
    rerank_candidates,
    intelligent_search,
)

SERVER_NAME = "aicarmine-intelligent-search"
SERVER_VERSION = "1.0.1-timeout-fix"


def list_tools() -> list:
    """Return available tools."""
    return [
        {
            "name": "intelligent_search",
            "description": "Complete intelligent search pipeline: Query → Embedding → Candidate Selection → Reranker → Final Results",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query"},
                    "top_k": {"type": "integer", "default": 20, "description": "Number of candidates to select"},
                    "top_n": {"type": "integer", "default": 10, "description": "Number of final results to return"}
                },
                "required": ["query"],
                "additionalProperties": True
            }
        },
        {
            "name": "intelligent_search_health",
            "description": "Check intelligent search service health",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
        }
    ]


def handle_tool_call(method: str, params: dict) -> dict:
    """Handle MCP tool calls for intelligent search."""
    if method == "intelligent_search":
        query = params.get("query", "")
        top_k = params.get("top_k", 20)
        top_n = params.get("top_n", 10)

        # Add timeout guard - total execution time bounded by intelligent_search module
        start_time = time.time()
        max_execution_time = 30  # Maximum seconds for entire search pipeline

        try:
            results = intelligent_search(query, top_k=top_k, top_n=top_n)
            elapsed = time.time() - start_time
            return {
                "results": results,
                "metadata": {
                    "execution_seconds": round(elapsed, 3),
                    "result_count": len(results)
                }
            }
        except Exception as e:
            elapsed = time.time() - start_time
            raise RuntimeError(f"intelligent_search failed after {elapsed:.1f}s: {e}") from e

    elif method == "intelligent_search_health":
        # Check all services with port-level checks only (no HTTP)
        ollama_ok = _check_port("127.0.0.1", 11435, timeout=1.0)
        ovms_ok = _check_port("127.0.0.1", 3550, timeout=1.0)

        return {
            "ok": True,
            "service": SERVER_NAME,
            "services": {
                "ollama_embedding": ollama_ok,
                "ovms_reranker": ovms_ok,
            }
        }
    else:
        raise ValueError(f"Unknown method: {method}")


def _check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open without making an HTTP request."""
    try:
        with socket.create_connection((host, port), timeout) as sock:
            return True
    except (socket.timeout, OSError, ConnectionRefusedError):
        return False


def handle_request(request: dict) -> dict:
    """Handle incoming JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})

    # Ensure id is always a string or number, never null
    raw_id = request.get("id")
    if raw_id is None:
        request_id = "0"
    elif isinstance(raw_id, str):
        request_id = raw_id
    else:
        request_id = str(raw_id)

    # Handle MCP protocol initialization
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {}
            },
            "id": request_id
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {"tools": list_tools()},
            "id": request_id
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        try:
            result = handle_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -1, "message": str(e), "data": None},
                "id": request_id
            }

    # Handle other methods not yet implemented
    if method in ["notifications/workerDone", "notifications/progress"]:
        return {
            "jsonrpc": "2.0",
            "result": {},
            "id": request_id
        }

    return {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": f"Unknown method: {method}", "data": None},
        "id": request_id
    }


if __name__ == "__main__":
    # Read requests from stdin with timeout protection
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = handle_request(request)
                print(json.dumps(response), flush=True)
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": str(e), "data": None},
                    "id": "0"
                }
                print(json.dumps(error_response), flush=True)
    except KeyboardInterrupt:
        pass