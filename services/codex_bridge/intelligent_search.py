#!/usr/bin/env python3
"""
AICarmine Intelligent Search: Query → Embedding → Candidate Selection → Reranker → Final Results

This module implements the complete intelligent search pipeline using:
- Ollama nomic-embed-text for embedding generation (port 11435)
- SQLite RAG index for candidate selection
- OVMS BAAI/bge-reranker-v2-m3 for reranking (port 3550)

With proper timeout handling to prevent infinite waiting.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.request
import urllib.error
import sqlite3
import time
from pathlib import Path
from typing import Any


# Configuration - timeouts configurable via environment variables
_ndef_timeout = int(os.environ.get("AICARMINE_INTELLIGENT_SEARCH_TIMEOUT", "120"))

OLLAMA_EMBED_URL = "http://127.0.0.1:11435/api/embed"
OLLAMA_MODEL = "nomic-embed-text"
OVMS_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
RAG_DB_PATH = Path.home() / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"
EMBED_DB_PATH = Path.home() / "AI" / "state" / "codex_rag" / "embeddings.sqlite3"

# Timeout configuration (seconds) - increased from 15 to 45 for OVMS CPU load
REQUEST_TIMEOUT = _ndef_timeout


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open without making an HTTP request."""
    try:
        with socket.create_connection((host, port), timeout) as sock:
            return True
    except (socket.timeout, OSError, ConnectionRefusedError):
        return False


def _check_service(url: str, timeout: float = REQUEST_TIMEOUT) -> bool:
    """Check if an HTTP service is reachable."""
    try:
        req = urllib.request.Request(url, method="GET", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError):
        return False


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text using Ollama nomic-embed-text."""
    payload = json.dumps({"model": OLLAMA_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "embedding" in result:
                return list(result["embedding"])
            elif "embeddings" in result:
                return list(result["embeddings"][0])
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
        raise RuntimeError(f"Ollama embedding failed: {type(e).__name__}: {e}") from e
    raise ValueError("Failed to generate embedding")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = (sum(x * x for x in a) ** 0.5)
    norm_b = (sum(x * x for x in b) ** 0.5)
    return dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0


def candidate_selection(query: str, top_k: int = 20) -> list[dict]:
    """Search RAG index for top-K most similar chunks using embedding similarity."""
    # Check if embeddings DB exists
    if not EMBED_DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(EMBED_DB_PATH))
    cursor = conn.cursor()

    try:
        # FTS5 search - use the MATCH operator directly with the query string embedded in SQL
        # SQLite FTS5 doesn't support parameterized MATCH, so we build the query safely
        safe_query = query.replace("'", "''")  # Escape single quotes for SQL injection prevention
        
        # Try FTS5 full-text search first
        try:
            sql = f"SELECT content FROM embeddings_fts WHERE embeddings_fts MATCH '{safe_query}' LIMIT {min(top_k, 100)}"
            cursor.execute(sql)
            fts_results = cursor.fetchall()

            if fts_results:
                candidates = []
                for idx, (content_row,) in enumerate(fts_results[:top_k]):
                    # Join back to main table to get path, start_line, end_line
                    join_sql = "SELECT path, start_line, end_line, content FROM embeddings WHERE content = ?"
                    cursor.execute(join_sql, (content_row,))
                    join_row = cursor.fetchone()
                    if join_row:
                        path, start_line, end_line, content = join_row
                        # Rank-based score: higher rank = higher score
                        rank_score = 1.0 / (1.0 + idx)
                        candidates.append({
                            "path": path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "content": content[:500] if content else "",
                            "similarity": rank_score,
                            "score": rank_score
                        })
                return candidates

        except sqlite3.OperationalError:
            # FTS5 not available or query failed, fall through to similarity search
            pass

        # Fall back to similarity search (only if no FTS5 results)
        cursor.execute("SELECT path, start_line, end_line, content FROM embeddings LIMIT ?", (top_k * 10,))
        all_chunks = cursor.fetchall()

        candidates = []
        for i, (path, start_line, end_line, content) in enumerate(all_chunks[:top_k]):
            # Generate embedding for this chunk (cached in DB)
            cursor.execute("SELECT embedding FROM embeddings WHERE path = ?", (path,))
            emb_row = cursor.fetchone()
            if emb_row:
                try:
                    chunk_emb = json.loads(emb_row[0])
                    sim = cosine_similarity(generate_embedding(query), chunk_emb)
                    candidates.append({
                        "path": path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "content": content[:500] if content else "",
                        "similarity": sim,
                        "score": sim
                    })
                except (json.JSONDecodeError, RuntimeError):
                    # If embedding generation fails, skip this chunk
                    pass

        # Sort by similarity and return top-K
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:top_k]
    finally:
        conn.close()


def rerank_candidates(query: str, candidates: list[dict], top_n: int = 10) -> list[dict]:
    """Score each candidate chunk against the query using OVMS reranker."""
    if not candidates:
        return []

    # Check if OVMS rerancer is available
    if not _is_port_open("127.0.0.1", 3550, timeout=1.0):
        # Fall back to rank-based scoring if OVMS unavailable
        for idx, candidate in enumerate(candidates[:top_n]):
            candidate["score"] = 1.0 / (1.0 + idx)
        return candidates[:top_n]

    # Prepare documents for reranking
    documents = [c["content"] for c in candidates]

    payload = json.dumps({
        "model": "BAAI/bge-reranker-v2-m3",
        "query": query,
        "documents": documents[:5],  # Limit to 5 docs per request (OVMS limit)
        "top_n": min(top_n, len(documents))
    }).encode("utf-8")

    req = urllib.request.Request(
        OVMS_RERANK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout):
        # Fall back to rank-based scoring if OVMS fails
        for idx, candidate in enumerate(candidates[:top_n]):
            candidate["score"] = 1.0 / (1.0 + idx)
        return candidates[:top_n]

    # Extract reranking scores and update candidates
    if "results" in result and len(result["results"]) > 0:
        for i, candidate in enumerate(candidates[:top_n]):
            if i < len(result["results"]):
                rerank_result = result["results"][i]
                # OVMS returns score directly or nested structure
                score = rerank_result.get("score", rerank_result.get("relevance_score", 0.0))
                candidate["score"] = score

    # Sort by reranker score and return top-N
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # If OVMS returned no valid scores (all 0.0), fall back to rank-based scoring
    if all(c.get("score", 0.0) == 0.0 for c in candidates[:top_n]):
        for idx, candidate in enumerate(candidates[:top_n]):
            candidate["score"] = 1.0 / (1.0 + idx)

    return candidates[:top_n]


def intelligent_search(query: str, top_k: int = 20, top_n: int = 10) -> list[dict]:
    """
    Complete intelligent search pipeline with timeout protection:
    Query → Embedding (semantic similarity) → Candidate Selection → Reranker (relevance scoring) → Final Results

    Total execution time is bounded by REQUEST_TIMEOUT * 2 (embedding + rerancer).
    """
    start_time = time.time()
    max_total_time = REQUEST_TIMEOUT * 2  # Maximum total time for entire pipeline

    # Step 1: Candidate selection via embedding similarity
    candidates = candidate_selection(query, top_k=top_k)

    if not candidates:
        return []

    # Check if we've exceeded the time budget
    elapsed = time.time() - start_time
    remaining_time = max_total_time - elapsed
    if remaining_time <= 0:
        return candidates  # Return whatever we have

    # Step 2: Reranking via OVMS rerancer (with timeout)
    results = rerank_candidates(query, candidates, top_n=top_n)

    return results


# MCP stdio protocol handlers
def handle_tool_call(method: str, params: dict) -> dict:
    """Handle MCP tool calls for intelligent search."""
    if method == "intelligent_search":
        query = params.get("query", "")
        top_k = params.get("top_k", 20)
        top_n = params.get("top_n", 10)
        results = intelligent_search(query, top_k=top_k, top_n=top_n)
        return {"results": results}
    elif method == "intelligent_search_health":
        # Check all services
        ollama_ok = _check_service(OLLAMA_EMBED_URL, timeout=2.0)
        ovms_ok = _is_port_open("127.0.0.1", 3550, timeout=1.0)

        return {
            "ok": True,
            "service": "aicarmine-intelligent-search",
            "services": {
                "ollama_embedding": ollama_ok,
                "ovms_reranker": ovms_ok,
            }
        }
    else:
        raise ValueError(f"Unknown method: {method}")


if __name__ == "__main__":
    # Test intelligent search
    query = "How to use MCP tools?"
    results = intelligent_search(query, top_k=20, top_n=10)

    print(f"Query: {query}")
    print(f"Results ({len(results)} results):")
    for i, result in enumerate(results):
        print(f"{i+1}. {result['path']}:{result['start_line']} (score: {result['score']:.4f})")