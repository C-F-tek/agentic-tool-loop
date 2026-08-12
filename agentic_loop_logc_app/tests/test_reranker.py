"""Tests for the RAG reranker module."""

from __future__ import annotations

import pytest
from ..rag.reranker import RAGReranker, _tokenize, _bm25_score, _tfidf_score, _keyword_overlap


class TestRAGReranker:
    """Test suite for RAGReranker."""
    
    def test_rerank_disabled(self):
        """Test that disabled reranker returns candidates unchanged."""
        reranker = RAGReranker(enabled=False)
        candidates = [{"content": "test"}, {"content": "test2"}]
        result = reranker.rerank("query", candidates)
        assert len(result) == 2
    
    def test_rerank_empty_candidates(self):
        """Test that empty candidates returns empty list."""
        reranker = RAGReranker()
        result = reranker.rerank("query", [])
        assert result == []
    
    def test_rerank_hybrid_strategy(self):
        """Test hybrid scoring strategy."""
        reranker = RAGReranker(strategy="hybrid")
        candidates = [
            {"content": "def hello(): print('world')"},
            {"content": "class World: pass"},
        ]
        result = reranker.rerank("hello world", candidates)
        assert len(result) == 2
        assert all("rerank_score" in c for c in result)
    
    def test_rerank_bm25_strategy(self):
        """Test BM25 scoring strategy."""
        reranker = RAGReranker(strategy="bm25")
        candidates = [
            {"content": "hello world hello"},
            {"content": "hello"},
        ]
        result = reranker.rerank("hello world", candidates)
        assert len(result) == 2
    
    def test_rerank_keyword_strategy(self):
        """Test keyword overlap strategy."""
        reranker = RAGReranker(strategy="keyword")
        candidates = [
            {"content": "hello world"},
            {"content": "goodbye world"},
        ]
        result = reranker.rerank("hello world", candidates)
        assert len(result) == 2
    
    def test_rerank_tf_idf_strategy(self):
        """Test TF-IDF scoring strategy."""
        reranker = RAGReranker(strategy="tfidf")
        candidates = [
            {"content": "hello world hello"},
            {"content": "hello"},
        ]
        result = reranker.rerank("hello world", candidates)
        assert len(result) == 2
    
    def test_rerank_http_strategy_fallback(self):
        """Test HTTP strategy falls back gracefully."""
        reranker = RAGReranker(strategy="http", rerank_url="http://invalid:9999/rerank")
        candidates = [{"content": "test"}]
        # Should not raise exception
        result = reranker.rerank("query", candidates)
        assert len(result) == 1
    
    def test_parse_results_dict(self):
        """Test parsing of reranker results from dict."""
        reranker = RAGReranker()
        
        # Test dict format with results key
        dict_result = reranker._parse_results({
            "results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 1, "relevance_score": 0.7},
            ]
        })
        assert len(dict_result) == 2
        assert dict_result[0]["index"] == 0
        assert dict_result[0]["score"] == 0.9
        
        # Test list format
        list_result = reranker._parse_results([
            {"index": 0, "relevance_score": 0.8},
        ])
        assert len(list_result) == 1
        
        # Test invalid format
        assert reranker._parse_results("invalid") == []


class TestTokenize:
    """Test suite for _tokenize function."""
    
    def test_basic_tokenize(self):
        """Test basic tokenization."""
        tokens = _tokenize("Hello World")
        assert tokens == ["hello", "world"]
    
    def test_empty_tokenize(self):
        """Test tokenization of empty string."""
        tokens = _tokenize("")
        assert tokens == []
    
    def test_punctuation_tokenize(self):
        """Test tokenization handles punctuation."""
        tokens = _tokenize("Hello, world!")
        assert tokens == ["hello", "world"]


class TestBM25Score:
    """Test suite for BM25 scoring."""
    
    def test_perfect_match(self):
        """Test BM25 with perfect match."""
        score = _bm25_score(["hello", "world"], ["hello", "world"])
        assert score > 0
    
    def test_no_match(self):
        """Test BM25 with no matching tokens."""
        score = _bm25_score(["goodbye", "world"], ["hello", "world"])
        # Should still have some score due to 'world' match
        assert score >= 0
    
    def test_empty_tokens(self):
        """Test BM25 with empty tokens."""
        score = _bm25_score([], ["hello"])
        assert score == 0


class TestTFIDFScore:
    """Test suite for TF-IDF scoring."""
    
    def test_high_frequency(self):
        """Test TF-IDF with high frequency term."""
        corpus = [
            ["hello", "world"],
            ["hello", "python"],
            ["hello", "world"],
        ]
        score = _tfidf_score(["hello"], corpus)
        assert score > 0
    
    def test_empty_doc(self):
        """Test TF-IDF with empty document."""
        score = _tfidf_score([], [["hello"]])
        assert score == 0


class TestKeywordOverlap:
    """Test suite for keyword overlap scoring."""
    
    def test_full_overlap(self):
        """Test keyword overlap with full overlap."""
        score = _keyword_overlap(["hello", "world"], ["hello", "world"])
        assert score == 1.0
    
    def test_partial_overlap(self):
        """Test keyword overlap with partial overlap."""
        score = _keyword_overlap(["hello", "world"], ["hello"])
        assert 0 < score < 1
    
    def test_no_overlap(self):
        """Test keyword overlap with no overlap."""
        score = _keyword_overlap(["goodbye"], ["hello"])
        assert score == 0