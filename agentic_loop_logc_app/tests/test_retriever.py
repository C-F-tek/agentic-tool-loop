"""Tests for the RAG retriever module."""

from __future__ import annotations

import tempfile
import sqlite3
import pytest
from pathlib import Path

from ..rag.retriever import RAGRetriever


def _create_test_db(db_path: Path) -> None:
    """Create a test database with sample chunks matching production schema."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_root TEXT DEFAULT '',
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                symbol TEXT DEFAULT '',
                kind TEXT DEFAULT '',
                content TEXT NOT NULL,
                content_hash TEXT DEFAULT '',
                updated_at REAL DEFAULT 0.0
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                repo_root, path, symbol, kind, content,
                content='chunks',
                content_rowid='id'
            )
        """)
        # Insert test data
        conn.execute(
            "INSERT INTO chunks (path, start_line, end_line, content) VALUES (?, ?, ?, ?)",
            ("test.py", 1, 10, "def hello(): print('world')"),
        )
        conn.execute("INSERT INTO chunks_fts (rowid, content) VALUES (1, 'def hello(): print world')")
        conn.commit()
    finally:
        conn.close()


class TestRAGRetriever:
    """Test suite for RAGRetriever."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file with test data."""
        db_path = None
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = Path(f.name)
            _create_test_db(db_path)
        yield db_path
        # Close any lingering handles by forcing GC
        import gc
        gc.collect()
        db_path.unlink(missing_ok=True)
    
    def test_retrieve_empty_query(self, temp_db):
        """Test that empty query returns no results."""
        retriever = RAGRetriever(index_db=temp_db)
        results = retriever.retrieve("")
        assert len(results) == 0
    
    def test_retrieve_returns_results(self, temp_db):
        """Test that retrieval returns results for valid query."""
        retriever = RAGRetriever(index_db=temp_db, candidate_limit=10)
        results = retriever.retrieve("hello")
        assert len(results) > 0