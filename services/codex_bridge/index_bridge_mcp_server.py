#!/usr/bin/env python3
"""
MCP server for index bridge — cross-reference RAG + Symbol Index without re-indexing.

Uses the SAME git candidate surface logic as existing RAG and Symbol Index,
but reads from their existing DBs instead of re-indexing files.

Provides:
  - aicarmine_index_bridge_health
  - aicarmine_index_bridge_build: Build cross-reference tables from existing indexes
  - aicarmine_index_bridge_query: Unified query across both indexes
  - aicarmine_index_bridge_persist: Persist symbol memory across server restarts
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-index-bridge-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Index Bridge Manager
# ---------------------------------------------------------------------------

class IndexBridgeManager:
    """Builds cross-reference tables from existing RAG + Symbol Index DBs.

    Does NOT re-index files. Reads from existing databases and builds
    a bridge layer that connects RAG chunks to symbol index entries.
    """

    def __init__(self, repo_root: str, rag_db_path: str, symbol_db_path: str) -> None:
        self.repo_root = Path(repo_root)
        self.rag_db_path = Path(rag_db_path)
        self.symbol_db_path = Path(symbol_db_path)
        self.bridge_db_path = Path(repo_root) / "state" / "index_bridge" / "bridge.sqlite3"
        self._lock = threading.Lock()
        self._init_bridge_db()

    def _init_bridge_db(self) -> None:
        """Initialize the bridge SQLite database schema."""
        db_dir = self.bridge_db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.bridge_db_path))
        cursor = conn.cursor()

        # Cross-reference table linking RAG chunks to symbols
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_symbol_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rag_chunk_id INTEGER NOT NULL,
                symbol_file_path TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                symbol_type TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Unified search index (combines RAG + Symbol Index data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unified_search_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                path TEXT NOT NULL,
                content TEXT,
                symbol_name TEXT,
                symbol_type TEXT,
                line_number INTEGER,
                content_hash TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Persistent symbol memory (survives server restarts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS persistent_symbol_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL DEFAULT 'repo',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                branch TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                confidence REAL DEFAULT 1.0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                UNIQUE(scope, key)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_path
            ON unified_search_index(path)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_symbol
            ON unified_search_index(symbol_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_persist_key
            ON persistent_symbol_memory(key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_persist_scope_key
            ON persistent_symbol_memory(scope, key)
        """)

        conn.commit()
        conn.close()

    def build_bridge(self) -> dict[str, Any]:
        """Build cross-reference tables from existing RAG + Symbol Index DBs.

        Reads from existing databases without re-indexing files.
        """
        if not self.rag_db_path.exists():
            return {"ok": False, "error": f"RAG DB not found: {self.rag_db_path}"}
        if not self.symbol_db_path.exists():
            return {"ok": False, "error": f"Symbol DB not found: {self.symbol_db_path}"}

        conn = sqlite3.connect(str(self.bridge_db_path))
        cursor = conn.cursor()

        # Step 1: Extract RAG chunks into unified index
        rag_conn = sqlite3.connect(str(self.rag_db_path))
        rag_conn.row_factory = sqlite3.Row
        rag_cursor = rag_conn.cursor()

        rag_cursor.execute("SELECT id, path, symbol, kind, content FROM chunks")
        rag_chunks = rag_cursor.fetchall()

        for chunk in rag_chunks:
            cursor.execute(
                """INSERT INTO unified_search_index
                   (source, path, content, symbol_name, symbol_type, line_number, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("rag", chunk["path"], chunk["content"][:10000],
                 chunk["symbol"] or "", chunk["kind"] or "", 0,
                 hashlib.sha256(chunk["content"].encode()).hexdigest()[:32])
            )

        # Step 2: Extract symbols into unified index
        sym_conn = sqlite3.connect(str(self.symbol_db_path))
        sym_conn.row_factory = sqlite3.Row
        sym_cursor = sym_conn.cursor()

        sym_cursor.execute("SELECT file_path, symbol_name, symbol_type, line_number FROM symbols")
        symbols = sym_cursor.fetchall()

        for sym in symbols:
            cursor.execute(
                """INSERT INTO unified_search_index
                   (source, path, content, symbol_name, symbol_type, line_number, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("symbol", sym["file_path"], "", sym["symbol_name"],
                 sym["symbol_type"], sym["line_number"],
                 hashlib.sha256(f"{sym['file_path']}:{sym['symbol_name']}".encode()).hexdigest()[:32])
            )

        # Step 3: Build chunk-symbol references
        # Match RAG chunks to symbols by file path
        for chunk in rag_chunks:
            if chunk["path"] and chunk["symbol"]:
                cursor.execute(
                    """INSERT INTO chunk_symbol_refs
                       (rag_chunk_id, symbol_file_path, symbol_name, symbol_type, confidence)
                       VALUES (?, ?, ?, ?, ?)""",
                    (chunk["id"], chunk["path"], chunk["symbol"], "unknown", 0.8)
                )

        conn.commit()

        # Count results
        unified_count = cursor.execute("SELECT COUNT(*) FROM unified_search_index").fetchone()[0]
        ref_count = cursor.execute("SELECT COUNT(*) FROM chunk_symbol_refs").fetchone()[0]
        persist_count = cursor.execute("SELECT COUNT(*) FROM persistent_symbol_memory").fetchone()[0]

        rag_conn.close()
        sym_conn.close()
        conn.close()

        return {
            "ok": True,
            "bridge_db": str(self.bridge_db_path),
            "unified_index_count": unified_count,
            "chunk_symbol_refs": ref_count,
            "persistent_memory_records": persist_count,
            "message": "Bridge built from existing RAG + Symbol Index DBs (no re-indexing)",
        }

    def query_unified(self, query: str, source: str = "all", limit: int = 20) -> dict[str, Any]:
        """Query across both RAG and Symbol Index via the bridge."""
        conn = sqlite3.connect(str(self.bridge_db_path))
        cursor = conn.cursor()

        if source == "all":
            cursor.execute(
                "SELECT * FROM unified_search_index WHERE path LIKE ? OR symbol_name LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
        elif source == "rag":
            cursor.execute(
                "SELECT * FROM unified_search_index WHERE source = 'rag' AND content LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            )
        else:  # symbol
            cursor.execute(
                "SELECT * FROM unified_search_index WHERE source = 'symbol' AND symbol_name LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            )

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return {
            "ok": True,
            "query": query,
            "source": source,
            "result_count": len(results),
            "results": results[:limit],
        }

    def persist_memory(self, key: str, value: str, scope: str = "repo",
                     source_type: str = "user", source_ref: str = "") -> dict[str, Any]:
        """Persist symbol memory across server restarts."""
        import hashlib

        conn = sqlite3.connect(str(self.bridge_db_path))
        cursor = conn.cursor()

        value_hash = hashlib.sha256(value.encode()).hexdigest()[:16]

        cursor.execute(
            """INSERT INTO persistent_symbol_memory
               (scope, key, value, source_type, source_ref, value_hash)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(scope, key) DO UPDATE SET
                   value=excluded.value,
                   updated_at=strftime('%s', 'now')""",
            (scope, key, value, source_type, source_ref, value_hash)
        )

        conn.commit()
        conn.close()

        return {
            "ok": True,
            "key": key,
            "scope": scope,
            "message": f"Memory persisted: {key}",
        }

    def get_persisted_memory(self, key: str | None = None, scope: str = "repo") -> dict[str, Any]:
        """Retrieve persisted symbol memory."""
        conn = sqlite3.connect(str(self.bridge_db_path))
        cursor = conn.cursor()

        if key:
            cursor.execute(
                "SELECT * FROM persistent_symbol_memory WHERE scope = ? AND key = ?",
                (scope, key)
            )
        else:
            cursor.execute(
                "SELECT * FROM persistent_symbol_memory WHERE scope = ?",
                (scope,)
            )

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "key": row[1],
                "value": row[2],
                "scope": row[3],
                "source_type": row[4],
                "source_ref": row[5],
                "status": row[6],
                "confidence": row[7],
                "tags": json.loads(row[8]) if row[8] else [],
                "created_at": row[9],
                "updated_at": row[10],
            })

        return {
            "ok": True,
            "scope": scope,
            "key": key,
            "record_count": len(results),
            "records": results,
        }


# Module-level singleton
_bridge: IndexBridgeManager | None = None
_lock = threading.Lock()


def _get_bridge(repo_root: str) -> IndexBridgeManager:
    global _bridge
    if _bridge is None:
        with _lock:
            if _bridge is None:
                rag_db = os.environ.get(
                    "AICARMINE_RAG_DB",
                    str(Path(repo_root) / "state" / "codex_rag" / "code_rag.sqlite3")
                )
                symbol_db = str(Path(repo_root) / "state" / "symbol_index" / "symbols.sqlite3")
                _bridge = IndexBridgeManager(repo_root, rag_db, symbol_db)
    return _bridge


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        bridge = _get_bridge(str(root))
        payload["index_bridge"] = {
            "enabled": True,
            "bridge_db": str(bridge.bridge_db_path),
            "rag_db": str(bridge.rag_db_path),
            "symbol_db": str(bridge.symbol_db_path),
        }
        return payload

    tools["aicarmine_index_bridge_health"] = ToolSpec(
        name="aicarmine_index_bridge_health",
        description="Report index bridge MCP health.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_index_bridge_build"] = ToolSpec(
        name="aicarmine_index_bridge_build",
        description="Build cross-reference tables from existing RAG + Symbol Index DBs (no re-indexing).",
        input_schema=object_schema(),
        handler=lambda args, root: _get_bridge(str(root)).build_bridge(),
    )

    tools["aicarmine_index_bridge_query"] = ToolSpec(
        name="aicarmine_index_bridge_query",
        description="Query across both RAG and Symbol Index via the bridge.",
        input_schema=object_schema({
            "query": {"type": "string"},
            "source": {"type": "string", "default": "all", "enum": ["all", "rag", "symbol"]},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200},
        }, required=["query"]),
        handler=lambda args, root: _get_bridge(str(root)).query_unified(
            args.get("query", ""),
            args.get("source", "all"),
            args.get("limit", 20)
        ),
    )

    tools["aicarmine_index_bridge_persist"] = ToolSpec(
        name="aicarmine_index_bridge_persist",
        description="Persist symbol memory across server restarts.",
        input_schema=object_schema({
            "key": {"type": "string"},
            "value": {"type": "string"},
            "scope": {"type": "string", "default": "repo"},
            "source_type": {"type": "string", "default": "user"},
            "source_ref": {"type": "string", "default": ""},
        }, required=["key", "value"]),
        handler=lambda args, root: _get_bridge(str(root)).persist_memory(
            args.get("key", ""),
            args.get("value", ""),
            args.get("scope", "repo"),
            args.get("source_type", "user"),
            args.get("source_ref", "")
        ),
    )

    tools["aicarmine_index_bridge_get_memory"] = ToolSpec(
        name="aicarmine_index_bridge_get_memory",
        description="Retrieve persisted symbol memory.",
        input_schema=object_schema({
            "key": {"type": "string"},
            "scope": {"type": "string", "default": "repo"},
        }),
        handler=lambda args, root: _get_bridge(str(root)).get_persisted_memory(
            args.get("key"),
            args.get("scope", "repo")
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
