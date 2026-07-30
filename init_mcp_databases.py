#!/usr/bin/env python3
"""Initialize all SQLite databases required by MCP servers."""
import sqlite3
import os
import sys
from datetime import datetime

base = r"C:\Users\sanit\agentic-tool-loop"

def main():
    # 1. RAG database - create chunks table and FTS5 virtual table
    rag_db = os.path.join(base, 'state', 'codex_rag', 'code_rag.sqlite3')
    conn = sqlite3.connect(rag_db)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY,
        path TEXT,
        start_line INTEGER,
        end_line INTEGER,
        symbol TEXT,
        kind TEXT,
        content TEXT
    )''')
    conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        content
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS index_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    now = datetime.now().isoformat()
    conn.execute("INSERT OR REPLACE INTO index_meta (key, value) VALUES ('indexed_at', ?)", (now,))
    conn.commit()
    conn.close()
    print(f'OK: RAG DB created at {rag_db}')

    # 2. Operational memory database
    op_db = os.path.join(base, 'output', 'ai_runtime_memory', 'operational_context.sqlite')
    conn = sqlite3.connect(op_db)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS operational_memory_records (
        record_id TEXT PRIMARY KEY,
        scope TEXT DEFAULT 'project',
        key TEXT,
        kind TEXT DEFAULT 'codex_note',
        summary TEXT,
        content TEXT,
        tags_json TEXT DEFAULT '[]',
        metadata_json TEXT DEFAULT '{}',
        confidence REAL DEFAULT 1.0,
        status TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_op_scope ON operational_memory_records(scope)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_op_status ON operational_memory_records(status)')
    conn.commit()
    conn.close()
    print(f'OK: Operational memory DB created at {op_db}')

    # 3. Persistent memory database
    pers_db = os.path.join(base, 'indexAI', 'agent_memory', 'agent_memory.sqlite')
    conn = sqlite3.connect(pers_db)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS memory_records (
        record_id TEXT PRIMARY KEY,
        scope TEXT DEFAULT 'repo',
        key TEXT,
        value TEXT,
        source_type TEXT,
        source_ref TEXT,
        kind TEXT DEFAULT 'verified_fact',
        summary TEXT,
        tags_json TEXT DEFAULT '[]',
        metadata_json TEXT DEFAULT '{}',
        confidence REAL DEFAULT 1.0,
        status TEXT DEFAULT 'active',
        branch TEXT,
        commit_sha TEXT,
        repo_root TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mem_scope ON memory_records(scope)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mem_key ON memory_records(scope, key)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mem_status ON memory_records(status)')
    conn.commit()
    conn.close()
    print(f'OK: Persistent memory DB created at {pers_db}')

    print('\nAll databases initialized successfully')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())