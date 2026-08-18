#!/usr/bin/env python3
"""Build embedding index from RAG chunks using Ollama nomic-embed-text."""
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

# DB paths
RAG_DB = Path(os.environ.get("USERPROFILE", Path.home())) / "AI" / "state" / "codex_rag" / "code_rag.sqlite3"
EMBED_DB = Path(os.environ.get("USERPROFILE", Path.home())) / "AI" / "state" / "codex_rag" / "embeddings.sqlite3"

# Ollama embedding service URL
OLLAMA_EMBED_URL = "http://127.0.0.1:11435/api/embed"
OLLAMA_MODEL = "nomic-embed-text"

def generate_embedding(text):
    """Generate embedding using Ollama nomic-embed-text model."""
    payload = json.dumps({"model": OLLAMA_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_EMBED_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if "embedding" in result:
            return list(result["embedding"])
        elif "embeddings" in result:
            return list(result["embeddings"][0])
    return None

def build_index():
    """Read RAG chunks and write embeddings."""
    print(f"Reading RAG DB from: {RAG_DB}")
    print(f"Writing embeddings to: {EMBED_DB}")
    
    conn = sqlite3.connect(str(RAG_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT path, start_line, end_line, symbol, kind, content FROM chunks")
    rows = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(rows)} chunks in RAG index")
    
    # Create embedding DB
    embed_conn = sqlite3.connect(str(EMBED_DB))
    embed_cursor = embed_conn.cursor()
    embed_cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            symbol TEXT,
            kind TEXT,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT
        )
    """)
    embed_cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_fts USING fts5(content)
    """)
    embed_conn.commit()
    
    total = len(rows)
    success = 0
    fail = 0
    
    for i, (path, start_line, end_line, symbol, kind, content) in enumerate(rows):
        # Generate embedding
        emb = generate_embedding(content)
        
        if emb:
            # Store as JSON blob
            emb_json = json.dumps(emb).encode("utf-8")
            meta_json = json.dumps({"path": path, "start_line": start_line, "end_line": end_line, "symbol": symbol, "kind": kind})
            
            embed_cursor.execute(
                "INSERT INTO embeddings (path, start_line, end_line, symbol, kind, content, embedding, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (path, start_line, end_line, symbol, kind, content, emb_json, meta_json)
            )
            embed_cursor.execute(
                "INSERT INTO embeddings_fts(content) VALUES (?)",
                (content,)
            )
            
            success += 1
        else:
            fail += 1
        
        if (i + 1) % 50 == 0 or i == total - 1:
            embed_conn.commit()
            print(f"Progress: {i+1}/{total} chunks processed. Success: {success}, Fail: {fail}")
    
    embed_conn.close()
    print(f"\nDone! Total: {total}, Success: {success}, Failed: {fail}")

if __name__ == "__main__":
    build_index()