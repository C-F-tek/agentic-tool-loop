#!/usr/bin/env python3
"""
AICarmine Embedding MCP Server

Provides MCP tools for:
1. Generate embeddings via OVMS (port 3551)
2. Store embeddings in the same SQLite DB used by RAG
3. Query embeddings for similarity search
4. Share the same code_rag.sqlite3 index with RAG

Tools:
  - aicarmine_embedding_generate: Generate embedding for text via OVMS
  - aicarmine_embedding_store: Store embeddings in SQLite DB
  - aicarmine_embedding_search: Search embeddings by similarity
  - aicarmine_embedding_index_status: Check embedding index status
  - aicarmine_embedding_reindex: Rebuild embedding index from git candidates
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any

SERVER_NAME = "aicarmine-embedding-mcp"
SERVER_VERSION = "1.0.0"

# OVMS embedding service URL
DEFAULT_EMBEDDING_URL = "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/infer"
DEFAULT_READY_URL = "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/ready"


def _default_db() -> Path:
    """Return the same SQLite DB path used by RAG."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"


def _log(message: str) -> None:
    debug = os.environ.get("AICARMINE_EMBEDDING_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    if debug:
        print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json_dumps(value)}], "isError": is_error}


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _check_ovms_ready(url: str = DEFAULT_READY_URL, timeout: int = 10) -> bool:
    """Check if OVMS embedding service is ready."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _generate_embedding(text: str, url: str = DEFAULT_EMBEDDING_URL, timeout: int = 30) -> list[float] | None:
    """Generate embedding for text using OVMS embedding service."""
    payload = json.dumps({"inputs": [{"content": text}]}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "outputs" in result:
                return result["outputs"][0]
    except Exception:
        return None


def _store_embeddings(texts: list[str], embeddings: list[list[float]]) -> bool:
    """Store embeddings in SQLite DB (same as RAG)."""
    db_path = _default_db()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for text, embedding in zip(texts, embeddings):
        cursor.execute(
            "INSERT INTO embeddings (text, embedding, metadata) VALUES (?, ?, ?)",
            (text, json.dumps(embedding), json.dumps({"source": "mcp"}))
        )
    conn.commit()
    conn.close()
    return True


def _search_embeddings(query: str, top_k: int = 5) -> list[dict]:
    """Search embeddings by similarity."""
    query_embedding = _generate_embedding(query)
    if not query_embedding:
        return []
    
    db_path = _default_db()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT text, embedding FROM embeddings")
    results = []
    for text, emb_bytes in cursor.fetchall():
        embedding = json.loads(emb_bytes)
        similarity = sum(a * b for a, b in zip(query_embedding, embedding))
        results.append({"text": text, "similarity": similarity})
    conn.close()
    return sorted(results, key=lambda x: x["similarity"], reverse=True)[:top_k]


def _handle_tool_call(method: str, params: dict) -> dict:
    """Handle MCP tool calls."""
    if method == "aicarmine_embedding_generate":
        text = params.get("text", "")
        embedding = _generate_embedding(text)
        return _ok(1, {"embedding": embedding[:10] if embedding else None})
    
    elif method == "aicarmine_embedding_store":
        texts = params.get("texts", [])
        embeddings = params.get("embeddings", [])
        success = _store_embeddings(texts=texts, embeddings=embeddings)
        return _ok(1, {"stored": success})
    
    elif method == "aicarmine_embedding_search":
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        results = _search_embeddings(query, top_k=top_k)
        return _ok(1, {"results": results})
    
    elif method == "aicarmine_embedding_index_status":
        db_path = _default_db()
        exists = os.path.exists(str(db_path))
        size = os.path.getsize(str(db_path)) if exists else 0
        ready = _check_ovms_ready()
        return _ok(1, {"db_exists": exists, "db_size": size, "ovms_ready": ready})
    
    elif method == "aicarmine_embedding_reindex":
        from rag_index_repo import build_index, MODE_DELTA, SOURCE_GIT_DEFAULT
        repo_root = Path(os.environ.get("AICARMINE_LAB_REPO", Path.cwd()))
        db_path = _default_db()
        build_index(repo_root, db_path, mode=MODE_DELTA, source=SOURCE_GIT_DEFAULT)
        return _ok(1, {"reindexed": True})
    
    elif method == "aicarmine_embedding_health":
        ovms_ready = _check_ovms_ready()
        db_path = _default_db()
        exists = os.path.exists(str(db_path))
        return _ok(1, {"ovms_ready": ovms_ready, "db_exists": exists})
    
    return _err(1, -32601, f"Unknown method: {method}")


def _read_stdin() -> str:
    """Read JSON-RPC request from stdin."""
    line = sys.stdin.readline()
    if not line:
        return ""
    length = int(line.strip())
    return sys.stdin.read(length)


def _write_response(response: dict) -> None:
    """Write JSON-RPC response to stdout."""
    body = json.dumps(response, ensure_ascii=False)
    print(f"Content-Length: {len(body)}\r\n\r\n{body}", end="")
    sys.stdout.flush()


def main() -> None:
    """Main MCP server loop."""
    _log("Starting AICarmine Embedding MCP Server")
    
    while True:
        try:
            request_json = _read_stdin()
            request = json.loads(request_json)
            
            method = request.get("method", "")
            params = request.get("params", {})
            msg_id = request.get("id", 0)
            
            _log(f"Handling {method}")
            result = _handle_tool_call(method, params)
            _write_response(result)
        except KeyboardInterrupt:
            break
        except Exception as e:
            _write_response(_err(0, -32603, f"Internal error: {str(e)}"))


if __name__ == "__main__":
    main()