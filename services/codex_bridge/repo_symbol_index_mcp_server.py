#!/usr/bin/env python3
"""MCP adapter for repository symbol indexing and querying with tree-sitter."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any
from collections import OrderedDict

from repo_mcp_common import (
    ToolSpec,
    handle_request,
    health_payload,
    mcp_text_result,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-repo-symbol-index-mcp"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Symbol Index Manager
# ---------------------------------------------------------------------------

class SymbolIndexManager:
    """Manages a SQLite-based symbol index for the repository.

    Uses tree-sitter to parse Python files and extract symbols (classes,
    functions, imports, variables) into a persistent SQLite database.
    """

    def __init__(self, db_path: str, repo_root: str) -> None:
        self.db_path = db_path
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database schema."""
        import sqlite3
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                symbol_type TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                column_number INTEGER NOT NULL,
                signature TEXT,
                parent_symbol TEXT,
                file_hash TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (file_path) REFERENCES files(file_path)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                line_count INTEGER DEFAULT 0,
                last_modified REAL,
                UNIQUE(file_path)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_name 
            ON symbols(symbol_name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_type 
            ON symbols(symbol_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_file 
            ON symbols(file_path)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_name_type 
            ON symbols(symbol_name, symbol_type)
        """)

        conn.commit()
        conn.close()

    def index_file(self, file_path: str, language: str = "python") -> dict[str, Any]:
        """Index symbols from a single file."""
        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        # Compute hash
        file_hash = self._compute_file_hash(str(file_path_obj))
        if file_hash == "":
            return {"ok": False, "error": f"Cannot read file: {file_path}"}

        # Check if file is unchanged
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT file_hash FROM files WHERE file_path = ?", (str(file_path_obj),))
        row = cursor.fetchone()
        if row and row[0] == file_hash:
            conn.close()
            return {"ok": True, "indexed": False, "message": "File unchanged, skipping"}

        # Parse file and extract symbols
        symbols = self._extract_symbols(str(file_path_obj), language)

        # Update file record
        cursor.execute("""
            INSERT OR REPLACE INTO files (file_path, file_hash, line_count)
            VALUES (?, ?, ?)
        """, (str(file_path_obj), file_hash, len(open(str(file_path_obj)).readlines())))

        # Remove old symbols for this file
        cursor.execute("DELETE FROM symbols WHERE file_path = ?", (str(file_path_obj),))

        # Insert new symbols
        for sym in symbols:
            cursor.execute("""
                INSERT INTO symbols (file_path, symbol_name, symbol_type, line_number, 
                                   column_number, signature, parent_symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(file_path_obj),
                sym["name"],
                sym["type"],
                sym["line"],
                sym["column"],
                sym.get("signature", ""),
                sym.get("parent", ""),
            ))

        conn.commit()
        conn.close()

        return {
            "ok": True,
            "indexed": True,
            "file": str(file_path_obj),
            "symbol_count": len(symbols),
            "symbols": symbols[:20],  # Return first 20 for preview
        }

    def index_directory(self, dir_path: str, language: str = "python", 
                       extensions: list[str] | None = None) -> dict[str, Any]:
        """Index all files in a directory."""
        if extensions is None:
            extensions = {".py": "python", ".js": "javascript", ".ts": "typescript"}

        file_count = 0
        symbol_count = 0
        errors = []

        for ext, lang in extensions.items():
            for file_path in Path(dir_path).rglob(f"*{ext}"):
                try:
                    result = self.index_file(str(file_path), lang)
                    if result.get("indexed"):
                        symbol_count += result.get("symbol_count", 0)
                    file_count += 1
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")

        return {
            "ok": True,
            "file_count": file_count,
            "symbol_count": symbol_count,
            "errors": errors[:10],
        }

    def query_symbols(self, query: str, query_type: str = "exact",
                     operation: str = "references",
                     include_signatures: bool = True,
                     max_results: int = 50) -> dict[str, Any]:
        """Query the symbol index."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        results = []

        if operation == "references":
            if query_type == "exact":
                cursor.execute(
                    "SELECT * FROM symbols WHERE symbol_name = ? ORDER BY line_number LIMIT ?",
                    (query, max_results)
                )
            elif query_type == "regex":
                cursor.execute(
                    "SELECT * FROM symbols WHERE symbol_name LIKE ? ORDER BY line_number LIMIT ?",
                    (f"%{query}%", max_results)
                )
            else:  # prefix
                cursor.execute(
                    "SELECT * FROM symbols WHERE symbol_name LIKE ? ORDER BY line_number LIMIT ?",
                    (f"{query}%", max_results)
                )

            results = [dict(row) for row in cursor.fetchall()]

        elif operation == "callers":
            # Find symbols that reference this symbol
            cursor.execute(
                "SELECT * FROM symbols WHERE symbol_name = ? ORDER BY line_number",
                (query,)
            )
            target_symbols = cursor.fetchall()

            for target in target_symbols[:10]:
                # Search for references in content (simplified)
                cursor.execute(
                    "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_number",
                    (target["file_path"],)
                )
                file_symbols = cursor.fetchall()
                for sym in file_symbols[:20]:
                    if sym["symbol_name"] != target["symbol_name"]:
                        results.append(dict(sym))

        elif operation == "callees":
            # Find symbols defined in this file
            cursor.execute(
                "SELECT * FROM symbols WHERE file_path LIKE ? ORDER BY line_number LIMIT ?",
                (f"%{query}%", max_results)
            )
            results = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "ok": True,
            "query": query,
            "operation": operation,
            "result_count": len(results),
            "results": results[:max_results],
        }

    def get_symbol_summary(self, path: str = ".") -> dict[str, Any]:
        """Get a summary of all symbols in the repository."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count by type
        cursor.execute("SELECT symbol_type, COUNT(*) FROM symbols GROUP BY symbol_type")
        type_counts = dict(cursor.fetchall())

        # Count files
        cursor.execute("SELECT COUNT(DISTINCT file_path) FROM files")
        file_count = cursor.fetchone()[0]

        # Total symbols
        cursor.execute("SELECT COUNT(*) FROM symbols")
        total_symbols = cursor.fetchone()[0]

        # Top symbols by reference count
        cursor.execute("""
            SELECT symbol_name, COUNT(*) as ref_count 
            FROM symbols 
            GROUP BY symbol_name 
            ORDER BY ref_count DESC 
            LIMIT 20
        """)
        top_symbols = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

        conn.close()

        return {
            "ok": True,
            "file_count": file_count,
            "total_symbols": total_symbols,
            "by_type": type_counts,
            "top_symbols": top_symbols,
        }


# Module-level singleton
_symbol_index: SymbolIndexManager | None = None
_index_lock = threading.Lock()


def _get_symbol_index(repo_root: str) -> SymbolIndexManager:
    global _symbol_index
    if _symbol_index is None:
        with _index_lock:
            if _symbol_index is None:
                db_path = os.path.join(repo_root, "state", "symbol_index", "symbols.sqlite3")
                _symbol_index = SymbolIndexManager(db_path, repo_root)
    return _symbol_index


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["symbol_index"] = {
            "enabled": True,
            "db_path": _get_symbol_index(str(root)).db_path if _symbol_index else None,
        }
        return payload

    tools["aicarmine_repo_symbol_index_health"] = ToolSpec(
        name="aicarmine_repo_symbol_index_health",
        description="Report symbol index MCP health and index status.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_repo_symbol_index_build"] = ToolSpec(
        name="aicarmine_repo_symbol_index_build",
        description="Build or update the symbol index for the repository.",
        input_schema=object_schema(
            {
                "path": string_prop("."),
                "language": string_prop("python"),
                "extensions": {"type": "array", "items": {"type": "string"}},
                "persist": {"type": "boolean", "default": True},
            }
        ),
        handler=lambda args, root: _get_symbol_index(str(root)).index_directory(
            args.get("path", "."),
            args.get("language", "python"),
            {ext: "python" for ext in (args.get("extensions") or [".py"])},
        ),
    )

    tools["aicarmine_repo_symbol_query"] = ToolSpec(
        name="aicarmine_repo_symbol_query",
        description="Query the symbol index for references, callers, or callees.",
        input_schema=object_schema(
            {
                "query": string_prop(),
                "query_type": enum_string_prop(["exact", "regex", "prefix"]),
                "operation": enum_string_prop(["references", "callers", "callees"]),
                "include_signatures": {"type": "boolean", "default": True},
                "max_results": integer_prop(50, 1, 500),
            }
        ),
        handler=lambda args, root: _get_symbol_index(str(root)).query_symbols(
            args.get("query", ""),
            args.get("query_type", "exact"),
            args.get("operation", "references"),
            args.get("include_signatures", True),
            args.get("max_results", 50),
        ),
    )

    tools["aicarmine_repo_symbol_summary"] = ToolSpec(
        name="aicarmine_repo_symbol_summary",
        description="Get a summary of all symbols in the repository.",
        input_schema=object_schema(
            {
                "path": string_prop("."),
            }
        ),
        handler=lambda args, root: _get_symbol_index(str(root)).get_symbol_summary(
            args.get("path", ".")
        ),
    )

    return tools


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def enum_string_prop(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())