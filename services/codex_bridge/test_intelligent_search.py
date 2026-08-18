#!/usr/bin/env python3
"""Test script for intelligent search MCP server."""
import json
import sys
import urllib.request

# Test 1: MCP stdio protocol - tools/list
print("=== Test 1: MCP tools/list ===")
sys.path.insert(0, "services/codex_bridge")
from intelligent_search_mcp_server import handle_request

resp = handle_request({"jsonrpc": "2.0", "method": "tools/list", "id": "1"})
print(json.dumps(resp, indent=2))

# Test 2: MCP health check
print("\n=== Test 2: MCP health check ===")
resp = handle_request({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "intelligent_search_health", "arguments": {}}})
print(json.dumps(resp, indent=2))

# Test 3: Ollama embedding service
print("\n=== Test 3: Ollama embedding service (port 11435) ===")
try:
    url = "http://127.0.0.1:11435/api/embed"
    payload = json.dumps({"model": "nomic-embed-text", "input": "test query"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"Ollama embedding OK: {list(data.keys())}")
except Exception as e:
    print(f"Ollama embedding FAILED: {e}")

# Test 4: OVMS reranker service
print("\n=== Test 4: OVMS reranker service (port 3550) ===")
try:
    url = "http://127.0.0.1:3550/v3/rerank"
    payload = json.dumps({"model": "BAAI/bge-reranker-v2-m3", "query": "test query", "documents": ["doc1", "doc2"]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"OVMS reranker OK: {list(data.keys())}")
except Exception as e:
    print(f"OVMS reranker FAILED: {e}")

# Test 5: SQLite embedding DB
print("\n=== Test 5: SQLite embedding DB ===")
import sqlite3
from pathlib import Path
db_path = Path.home() / "AI" / "state" / "codex_rag" / "embeddings.sqlite3"
try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"SQLite DB at {db_path}")
    print(f"Tables: {[t[0] for t in tables]}")
    conn.close()
except Exception as e:
    print(f"SQLite DB FAILED: {e}")