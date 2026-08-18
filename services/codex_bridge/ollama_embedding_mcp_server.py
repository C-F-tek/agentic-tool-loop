#!/usr/bin/env python3
"""
AICarmine Ollama Embedding MCP Server (Cline-compatible)

Uses Ollama's /api/embed endpoint to generate real FP32 embeddings.
Model: nomic-embed-text (768-dimensional vectors).

MCP stdio protocol:
  - Read JSON-RPC requests from stdin
  - Write JSON-RPC responses to stdout
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any

SERVER_NAME = "aicarmine-ollama-embedding-mcp"
SERVER_VERSION = "1.0.0"

# Ollama embedding service URL (port 11435)
OLLAMA_EMBEDDING_URL = "http://127.0.0.1:11435/api/embed"
OLLAMA_MODEL = "nomic-embed-text"

# Tool schemas for MCP tools/list
TOOL_SCHEMAS = [
    {
        "name": "ollama_embedding_health",
        "description": "Check Ollama embedding service health on port 11435",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "ollama_embedding_list_models",
        "description": "List available Ollama embedding models",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "ollama_embedding_embed_text",
        "description": "Generate embedding for a single text via Ollama nomic-embed-text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Input text to embed"}},
            "required": ["text"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_embedding_embed_batch",
        "description": "Generate embeddings for multiple texts via Ollama",
        "inputSchema": {
            "type": "object",
            "properties": {"texts": {"type": "array", "items": {"type": "string"}, "description": "List of input texts to embed"}},
            "required": ["texts"],
            "additionalProperties": True
        }
    },
    {
        "name": "embedding_search",
        "description": "Search embeddings by similarity in SQLite DB using Ollama embeddings",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query text"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"}
            },
            "required": ["query"],
            "additionalProperties": True
        }
    },
    {
        "name": "embedding_similarity",
        "description": "Compute similarity between two texts via Ollama embeddings",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text1": {"type": "string", "description": "First text"},
                "text2": {"type": "string", "description": "Second text"}
            },
            "required": ["text1", "text2"],
            "additionalProperties": True
        }
    },
    {
        "name": "embedding_mcp_health",
        "description": "Check embedding MCP server health (DB + Ollama)",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "aicarmine_embedding_health",
        "description": "Alias for embedding MCP health check",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    }
]


def _default_db() -> Path:
    db_path = os.environ.get("AICARMINE_RAG_DB")
    if db_path:
        return Path(db_path)
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _log(message: str) -> None:
    debug = os.environ.get("AICARMINE_OLLAMA_EMBEDDING_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    if debug:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _check_ollama_ready(url: str = OLLAMA_EMBEDDING_URL, timeout: int = 10) -> bool:
    """Check if Ollama embedding service is ready."""
    try:
        payload = json.dumps({"model": OLLAMA_MODEL, "input": ""}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
            return "embedding" in data or "embeddings" in data
    except Exception:
        return False


def _generate_embedding(text: str, url: str = OLLAMA_EMBEDDING_URL, timeout: int = 30) -> list[float] | None:
    """Generate embedding using Ollama nomic-embed-text model."""
    try:
        payload = json.dumps({"model": OLLAMA_MODEL, "input": text}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "embedding" in result:
                return list(result["embedding"])
            elif "embeddings" in result:
                return list(result["embeddings"][0])
    except Exception as e:
        _log(f"Embedding generation failed: {e}")
    return None


def _handle_tool_call(method: str, params: dict) -> dict:
    """Handle MCP tool calls."""
    if method == "ollama_embedding_health":
        ollama_ready = _check_ollama_ready()
        db_path = _default_db()
        exists = os.path.exists(str(db_path))
        return {"content": [{"type": "text", "text": json.dumps({"ollama_ready": ollama_ready, "db_exists": exists})}]}

    elif method == "ollama_embedding_list_models":
        try:
            url = "http://127.0.0.1:11435/api/tags"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return {"content": [{"type": "text", "text": json.dumps({"status": "success", "models": models})}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}

    elif method == "ollama_embedding_embed_text":
        text = params.get("text", "")
        if not text:
            return {"content": [{"type": "text", "text": json.dumps({"error": "text is required"})}], "isError": True}
        embedding = _generate_embedding(text)
        if embedding:
            return {"content": [{"type": "text", "text": json.dumps({"embedding_shape": len(embedding), "first_5": embedding[:5], "success": True})}]}
        return {"content": [{"type": "text", "text": json.dumps({"error": "embedding generation failed"})}], "isError": True}

    elif method == "ollama_embedding_embed_batch":
        texts = params.get("texts", [])
        if not texts:
            return {"content": [{"type": "text", "text": json.dumps({"error": "texts array is required"})}], "isError": True}
        results = []
        for text in texts:
            emb = _generate_embedding(text)
            results.append({"text": text, "embedding_shape": len(emb) if emb else None})
        return {"content": [{"type": "text", "text": json.dumps({"results": results})}]}

    elif method == "embedding_search":
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        query_embedding = _generate_embedding(query)
        if not query_embedding:
            return {"content": [{"type": "text", "text": json.dumps({"results": []})}]}
        db_path = _default_db()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT text, embedding FROM embeddings")
        results = []
        for row_text, emb_bytes in cursor.fetchall():
            embedding = json.loads(emb_bytes)
            similarity = sum(a * b for a, b in zip(query_embedding, embedding))
            results.append({"text": row_text, "similarity": similarity})
        conn.close()
        return {"content": [{"type": "text", "text": json.dumps({"results": sorted(results, key=lambda x: x["similarity"], reverse=True)[:top_k]})}]}

    elif method == "embedding_similarity":
        text1 = params.get("text1", "")
        text2 = params.get("text2", "")
        emb1 = _generate_embedding(text1)
        emb2 = _generate_embedding(text2)
        if not emb1 or not emb2:
            return {"content": [{"type": "text", "text": json.dumps({"similarity": None})}]}
        similarity = sum(a * b for a, b in zip(emb1, emb2))
        return {"content": [{"type": "text", "text": json.dumps({"similarity": similarity})}]}

    elif method == "embedding_mcp_health" or method == "aicarmine_embedding_health":
        ollama_ready = _check_ollama_ready()
        db_path = _default_db()
        exists = os.path.exists(str(db_path))
        size = os.path.getsize(str(db_path)) if exists else 0
        return {"content": [{"type": "text", "text": json.dumps({"ollama_ready": ollama_ready, "db_exists": exists, "db_size": size})}]}

    return {"content": [{"type": "text", "text": json.dumps({"error": f"Unknown method: {method}"})}], "isError": True}


def _read_message() -> str:
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.strip()


def _write_response(response: dict) -> None:
    body = json.dumps(response, ensure_ascii=False)
    print(body, end="\n")
    sys.stdout.flush()


def main() -> None:
    _log("Starting AICarmine Ollama Embedding MCP Server (Cline-compatible)")

    while True:
        try:
            request_json = _read_message()
            if not request_json.strip():
                continue
            request = json.loads(request_json)

            method = request.get("method", "")
            params = request.get("params", {}) if isinstance(request.get("params"), dict) else {}
            msg_id = request.get("id", 0)

            _log(f"Handling {method}")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": False, "listChanged": False},
                            "prompts": {"listChanged": False},
                            "roots": {"listChanged": False},
                        },
                        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    },
                }
                _write_response(response)
                continue

            if method == "tools/list":
                response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_SCHEMAS}}
                _write_response(response)
                continue

            if method == "tools/call":
                name = params.get("name", "")
                arguments = params.get("arguments", {}) if isinstance(params.get("arguments"), dict) else {}
                result = _handle_tool_call(name, arguments)
                response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
                _write_response(response)
                continue

            if method.startswith("notifications/"):
                continue

        except KeyboardInterrupt:
            break
        except json.JSONDecodeError as e:
            _write_response({"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": f"Parse error: {str(e)}"}})
        except Exception as e:
            _write_response({"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": f"Internal error: {str(e)}"}})


if __name__ == "__main__":
    main()