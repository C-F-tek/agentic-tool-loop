"""Tests for the RAG agent module."""

from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

from agents.rag_agent import DataRAGAgent, QueryResult


class TestDataRAGAgent:
    """Test suite for DataRAGAgent."""
    
    @pytest.fixture
    def temp_config(self):
        """Create a temporary config directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    def test_agent_initialization(self, temp_config):
        """Test agent initialization."""
        agent = DataRAGAgent()
        assert agent.indexer is not None
        assert agent.retriever is not None
        assert agent.reranker is not None
    
    def test_query_result(self):
        """Test QueryResult dataclass."""
        result = QueryResult(answer="test answer", confidence=0.8)
        assert result.answer == "test answer"
        assert result.confidence == 0.8
        assert len(result.sources) == 0
    
    def test_build_index_signature(self, temp_config):
        """Test that build_index method exists and has correct signature."""
        agent = DataRAGAgent()
        assert hasattr(agent, 'build_index')
        assert callable(agent.build_index)
    
    def test_query_signature(self, temp_config):
        """Test that query method exists and has correct signature."""
        agent = DataRAGAgent()
        assert hasattr(agent, 'query')
        assert callable(agent.query)