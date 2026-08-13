"""
RAG Retriever - Retrieves relevant chunks from the RAG index.

This module handles FTS5 search and candidate retrieval from the SQLite index.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    rank: int
    score: float | None
    path: str
    start_line: int
    end_line: int
    symbol: str
    kind: str
    content: str


@dataclass
class RAGRetriever:
    """RAG retriever for querying the SQLite FTS5 index."""
    
    index_db: Path
    candidate_limit: int = 80
    top_k: int = 12
    
    def __post_init__(self) -> None:
        """Validate index database exists."""
        if not self.index_db.exists():
            logger.warning(f"Index database does not exist: {self.index_db}")
    
    def retrieve(self, query: str) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for the given query."""
        if not query.strip():
            return []
        
        conn = sqlite3.connect(f"file:{self.index_db.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            candidates = self._fts_query(conn, query)
            logger.info(f"FTS query returned {len(candidates)} candidates")
            return candidates[:self.candidate_limit]
        finally:
            conn.close()
    
    def _fts_query(self, conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
        """Execute FTS5 query against the index."""
        tokens = re.findall(r"[A-Za-z0-9_./:-]{2,}", query)
        tokens = [token[:96].replace('"', '""') for token in tokens][:40]
        if not tokens:
            return self._fallback_like_query(conn, query)
        
        match = " AND ".join([f'"{t}"' for t in tokens])
        
        try:
            # Query FTS5 via subquery on rowid - FTS5 virtual tables expose
            # `rowid` only as an implicit column usable in WHERE/ORDER BY, not
            # as a joinable column in JOIN ... ON clauses.
            rows = conn.execute(
                """
                SELECT
                    id, path, start_line, end_line, symbol, kind, content,
                    0.0 AS rank
                FROM chunks
                WHERE id IN (
                    SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?
                )
                ORDER BY rank
                LIMIT ?
                """,
                (match, self.candidate_limit),
            ).fetchall()
            
            if not rows:
                logger.info("FTS5 MATCH returned no results, trying OR query")
                # Try OR query instead of AND
                or_match = " OR ".join([f'"{t}"' for t in tokens])
                rows = conn.execute(
                    """
                    SELECT
                        id, path, start_line, end_line, symbol, kind, content,
                        0.0 AS rank
                    FROM chunks
                    WHERE id IN (
                        SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?
                    )
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (or_match, self.candidate_limit),
                ).fetchall()
            
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"FTS match failed: {e}, falling back to LIKE query")
            return self._fallback_like_query(conn, query)
    
    def _fallback_like_query(self, conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
        """Fallback LIKE-based query if FTS fails."""
        # Try token-based LIKE first
        tokens = re.findall(r"[A-Za-z0-9_]{3,}", query)
        if tokens:
            like_parts = " OR ".join([f"content LIKE '%{t}%'" for t in tokens[:5]])
            like_query = f"SELECT id, path, start_line, end_line, symbol, kind, content, 0.0 AS rank FROM chunks WHERE {like_parts} ORDER BY id DESC LIMIT ?"
            rows = conn.execute(like_query, (self.candidate_limit,)).fetchall()
            if rows:
                return [dict(r) for r in rows]
        
        # Full fallback
        like = f"%{query[:200]}%"
        rows = conn.execute(
            """
            SELECT id, path, start_line, end_line, symbol, kind, content, 0.0 AS rank
            FROM chunks
            WHERE content LIKE ? OR path LIKE ? OR symbol LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (like, like, like, self.candidate_limit),
        ).fetchall()
        return [dict(r) for r in rows]
