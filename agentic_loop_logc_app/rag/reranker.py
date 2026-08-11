"""
RAG Reranker - Reranks retrieved chunks using multiple strategies.

This module provides reranking capabilities using:
1. TF-IDF based scoring (pure Python, no external dependencies)
2. BM25-style scoring
3. Keyword overlap scoring
4. HTTP-based reranking (optional OVMS/Ollama endpoint)

All methods are pure Python with no external service dependencies.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words."""
    return [m.lower() for m in re.findall(r'\b\w+\b', text.lower())]


def _tfidf_score(doc_tokens: list[str], corpus_tokens: list[list[str]]) -> float:
    """Calculate simple TF-IDF score for a document."""
    if not doc_tokens:
        return 0.0
    
    counter = Counter(doc_tokens)
    tf = sum(counter.values())
    max_tf = counter.most_common(1)[0][1] if counter else 1
    
    idf = 0.0
    total_docs = len(corpus_tokens) if corpus_tokens else 1
    for token in counter:
        doc_count = sum(1 for doc in corpus_tokens if token in doc)
        idf += (1 + doc_count / total_docs) if total_docs > 0 else 1
    
    return (max_tf / tf) * idf if tf > 0 else 0.0


def _bm25_score(doc_tokens: list[str], query_tokens: list[str], 
                k1: float = 1.6, b: float = 0.75) -> float:
    """Calculate simplified BM25 score."""
    if not doc_tokens or not query_tokens:
        return 0.0
    
    doc_len = len(doc_tokens)
    matches = 0
    doc_counter = Counter(doc_tokens)
    for token in query_tokens:
        matches += doc_counter.get(token, 0)
    
    numerator = matches * (k1 + 1)
    denominator = matches + k1 * (1 - b) + b * doc_len
    
    if denominator == 0:
        return 0.0
    
    score = numerator / denominator
    return score * (matches / len(query_tokens)) if query_tokens else 0.0


def _keyword_overlap(doc_tokens: list[str], query_tokens: list[str]) -> float:
    """Calculate keyword overlap score."""
    if not doc_tokens or not query_tokens:
        return 0.0
    
    doc_set = set(doc_tokens)
    query_set = set(query_tokens)
    
    intersection = doc_set & query_set
    union = doc_set | query_set
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


@dataclass
class RAGReranker:
    """RAG reranker with multiple scoring strategies."""
    
    rerank_url: str = "http://127.0.0.1:3550/v3/rerank"
    model: str = "BAAI/bge-reranker-v2-m3"
    enabled: bool = True
    candidate_limit: int = 12
    doc_chars: int = 2500
    timeout_seconds: float = 30.0
    
    strategy: str = "hybrid"
    bm25_weight: float = 0.5
    tfidf_weight: float = 0.3
    keyword_weight: float = 0.2
    
    def __post_init__(self) -> None:
        valid_strategies = ["bm25", "tfidf", "keyword", "http", "hybrid"]
        if self.strategy not in valid_strategies:
            logger.warning(f"Invalid strategy '{self.strategy}', defaulting to 'hybrid'")
            self.strategy = "hybrid"
    
    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.enabled or not candidates:
            return candidates
        
        query_tokens = _tokenize(query)
        docs = [str(c.get("content") or "")[:self.doc_chars] for c in candidates]
        doc_tokens = [_tokenize(doc) for doc in docs]
        
        scores = []
        
        if self.strategy == "http":
            scores = self._http_rerank(query, candidates)
        elif self.strategy == "hybrid":
            scores = self._hybrid_score(doc_tokens, query_tokens)
        elif self.strategy == "bm25":
            scores = [_bm25_score(doc, query_tokens) for doc in doc_tokens]
        elif self.strategy == "tfidf":
            scores = [_tfidf_score(doc, doc_tokens) for doc in doc_tokens]
        elif self.strategy == "keyword":
            scores = [_keyword_overlap(doc, query_tokens) for doc in doc_tokens]
        else:
            scores = [0.0] * len(candidates)
        
        for i, candidate in enumerate(candidates):
            merged = dict(candidate)
            merged["rerank_score"] = scores[i] if i < len(scores) else 0.0
            candidates[i] = merged
        
        sorted_candidates = sorted(candidates, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        ranked = sorted_candidates[:self.candidate_limit]
        
        ranked_indices = {id(c) for c in ranked}
        for candidate in candidates:
            if id(candidate) not in ranked_indices:
                candidate["rerank_score"] = None
                ranked.append(candidate)
        
        logger.info(f"Reranked {len(candidates)} candidates using '{self.strategy}' strategy")
        return ranked
    
    def _hybrid_score(self, doc_tokens: list[list[str]], query_tokens: list[str]) -> list[float]:
        scores = []
        for doc in doc_tokens:
            bm25 = _bm25_score(doc, query_tokens)
            tfidf = _tfidf_score(doc, doc_tokens)
            keyword = _keyword_overlap(doc, query_tokens)
            
            score = (
                self.bm25_weight * bm25 +
                self.tfidf_weight * tfidf +
                self.keyword_weight * keyword
            )
            scores.append(score)
        
        return scores
    
    def _http_rerank(self, query: str, candidates: list[dict]) -> list[float]:
        try:
            docs = [str(c.get("content") or "")[:self.doc_chars] for c in candidates]
            payload = {
                "model": self.model,
                "query": query,
                "documents": docs,
            }
            
            response = self._http_json("POST", self.rerank_url, payload)
            parsed = self._parse_results(response)
            
            if not parsed:
                return [0.0] * len(candidates)
            
            score_map = {item["index"]: item["score"] for item in parsed}
            return [score_map.get(i, 0.0) for i in range(len(candidates))]
            
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            logger.warning(f"HTTP reranker unavailable: {e}")
            return [0.0] * len(candidates)
    
    def _http_json(self, method: str, url: str, payload: Any | None = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        with urllib.request.urlopen(req, timeout=int(self.timeout_seconds)) as res:
            raw = res.read()
            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                return {"status": getattr(res, "status", None)}
            if "application/json" in (res.headers.get("Content-Type") or "").lower() or text.strip().startswith(("{", "[")):
                return json.loads(text)
            return {"status": getattr(res, "status", None), "text": text[:2000]}
    
    def _parse_results(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            raw_results = value.get("results") or value.get("data") or []
        elif isinstance(value, list):
            raw_results = value
        else:
            return []
        
        out = []
        for position, item in enumerate(raw_results):
            if not isinstance(item, dict):
                continue
            index = item.get("index", item.get("document_index", item.get("id", position)))
            try:
                idx = int(index)
            except (TypeError, ValueError):
                idx = position
            score = item.get("relevance_score", item.get("score", item.get("logit", 0.0)))
            try:
                score_value = float(score)
            except (TypeError, ValueError):
                score_value = 0.0
            out.append({"index": idx, "score": score_value, "raw": item})
        return out