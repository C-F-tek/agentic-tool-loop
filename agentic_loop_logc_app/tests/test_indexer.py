"""Tests for the RAG indexer module."""

from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

from rag.indexer import RAGIndexer, ChunkInfo


class TestRAGIndexer:
    """Test suite for RAGIndexer."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            yield f.name
            Path(f.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with sample files."""
        with tempfile.TemporaryDirectory() as dir_path:
            path = Path(dir_path)
            # Create sample Python file
            py_file = path / "sample.py"
            py_file.write_text("def hello():\n    print('world')\n")
            # Create sample Markdown file
            md_file = path / "sample.md"
            md_file.write_text("# Title\n\nThis is a test.\n")
            yield path
    
    def test_init_schema(self, temp_db):
        """Test that the schema is initialized correctly."""
        indexer = RAGIndexer(index_db=Path(temp_db))
        assert Path(temp_db).exists()
    
    def test_discover_files(self, temp_dir):
        """Test file discovery."""
        indexer = RAGIndexer(index_db=Path(tempfile.mktemp(suffix=".sqlite3")))
        files = indexer._discover_files(str(temp_dir), "filesystem")
        assert len(files) == 2
        assert any(".py" in f for f in files)
        assert any(".md" in f for f in files)
    
    def test_index_file(self, temp_dir):
        """Test indexing a single file."""
        indexer = RAGIndexer(index_db=Path(tempfile.mktemp(suffix=".sqlite3")), chunk_lines=10)
        chunks = indexer._index_file(str(temp_dir / "sample.py"))
        assert len(chunks) > 0
        assert isinstance(chunks[0], ChunkInfo)
    
    def test_build_index(self, temp_dir, temp_db):
        """Test building the full index."""
        indexer = RAGIndexer(index_db=Path(temp_db))
        result = indexer.build_index(str(temp_dir), "filesystem")
        assert result["ok"] is True
        assert result["files_indexed"] == 2
        assert result["total_chunks"] > 0