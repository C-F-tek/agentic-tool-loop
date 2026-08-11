"""
RAG Indexer - Builds and maintains the RAG index for data querying.

This module handles indexing of database schemas, sample data, and related files
into a SQLite FTS5 index for retrieval.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about an indexed chunk."""
    path: str
    start_line: int
    end_line: int
    symbol: str = ""
    kind: str = ""
    content: str = ""
    score: float = 0.0


@dataclass
class RAGIndexer:
    """RAG indexer for building and maintaining the SQLite FTS5 index."""
    
    index_db: Path
    chunk_chars: int = 4000
    chunk_lines: int = 180
    max_file_bytes: int = 2000000
    
    def __post_init__(self) -> None:
        """Initialize the indexer database schema."""
        self.index_db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _init_schema(self) -> None:
        """Create the RAG index schema if it doesn't exist."""
        conn = sqlite3.connect(str(self.index_db))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    symbol TEXT DEFAULT '',
                    kind TEXT DEFAULT '',
                    content TEXT NOT NULL
                )
            """)
            # Check if FTS table exists before creating
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'").fetchall()
            if not tables:
                conn.execute("""
                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        content
                    )
                """)
            conn.commit()
        finally:
            conn.close()
    
    def build_index(self, source_path: str = ".", source_type: str = "filesystem") -> dict[str, Any]:
        """Build the RAG index from the specified source."""
        logger.info(f"Building index from {source_path} ({source_type})")
        
        conn = sqlite3.connect(str(self.index_db))
        try:
            # Clear existing index for full rebuild
            conn.execute("DELETE FROM chunks_fts")
            conn.execute("DELETE FROM chunks")
            conn.commit()
            
            files = self._discover_files(source_path, source_type)
            total_chunks = 0
            
            for file_path in files:
                chunks = self._index_file(file_path)
                total_chunks += len(chunks)
                self._insert_chunks(conn, chunks)
            
            conn.commit()
            
            result = {
                "ok": True,
                "source": source_path,
                "source_type": source_type,
                "files_indexed": len(files),
                "total_chunks": total_chunks,
            }
            logger.info(f"Index built: {result}")
            return result
        finally:
            conn.close()
    
    def _discover_files(self, source_path: str, source_type: str) -> list[str]:
        """Discover files to index based on source type."""
        path = Path(source_path)
        if not path.exists():
            logger.warning(f"Source path does not exist: {source_path}")
            return []
        
        suffixes = [".py", ".md", ".yaml", ".yml", ".json", ".csv", ".sql", ".txt"]
        files = []
        
        for suffix in suffixes:
            for f in path.rglob(f"*{suffix}"):
                if f.is_file() and f.stat().st_size <= self.max_file_bytes:
                    files.append(str(f))
        
        logger.info(f"Discovered {len(files)} files from {source_path}")
        return files
    
    def _index_file(self, file_path: str) -> list[ChunkInfo]:
        """Index a single file into chunks."""
        path = Path(file_path)
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return []
        
        lines = content.split("\n")
        chunks = []
        
        for start in range(0, len(lines), self.chunk_lines):
            end = min(start + self.chunk_lines, len(lines))
            chunk_content = "\n".join(lines[start:end])
            
            if len(chunk_content) > self.chunk_chars:
                chunk_content = chunk_content[:self.chunk_chars]
            
            chunks.append(ChunkInfo(
                path=file_path,
                start_line=start + 1,
                end_line=end,
                content=chunk_content,
            ))
        
        logger.debug(f"Indexed {len(chunks)} chunks from {file_path}")
        return chunks
    
    def _insert_chunks(self, conn: sqlite3.Connection, chunks: list[ChunkInfo]) -> None:
        """Insert chunks into the database."""
        for chunk in chunks:
            # Insert into main chunks table
            conn.execute(
                "INSERT INTO chunks (path, start_line, end_line, symbol, kind, content) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk.path, chunk.start_line, chunk.end_line, chunk.symbol, chunk.kind, chunk.content),
            )
            # Insert into FTS5 table separately (no sync needed with standalone FTS5)
            conn.execute(
                "INSERT INTO chunks_fts (content) VALUES (?)",
                (chunk.content,),
            )
