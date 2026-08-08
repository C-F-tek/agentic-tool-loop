"""RAG cache management for intrinsic_context retrieval.

This module manages caching of RAG SQLite query results to prevent redundant queries
and optimize intrinsic_context budget usage. The cache is keyed by goal tokens
to identify semantically equivalent queries.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "rag"
CACHE_FILE = CACHE_DIR / "intrinsic_context_cache.json"


def _goal_hash(goal: str) -> str:
    """Compute hash of goal tokens for cache key."""
    tokens = goal.lower().split()[:8]  # Use first 8 words
    text = " ".join(tokens)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _load_cache() -> dict[str, Any]:
    """Load RAG cache from disk."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    """Save RAG cache to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def get_cached_rag_result(
    goal: str,
    db_path: Path,
    top_k: int = 6,
    char_budget: int = 10000,
) -> dict[str, Any] | None:
    """Get cached RAG result if available.
    
    Args:
        goal: Search goal string
        db_path: Path to RAG SQLite database
        top_k: Maximum number of chunks to return
        char_budget: Character budget for context
        
    Returns:
        Cached result dict or None if no cache hit
    """
    cache = _load_cache()
    goal_hash = _goal_hash(goal)
    
    if goal_hash not in cache:
        return None
    
    cached = cache[goal_hash]
    status = cached.get("status")
    
    # Return cached result only if it's ready and db exists
    if status == "ready" and db_path.exists():
        return cached
    
    return None


def invalidate_rag_cache(goal: str) -> None:
    """Invalidate cache entry for a specific goal."""
    cache = _load_cache()
    goal_hash = _goal_hash(goal)
    cache.pop(goal_hash, None)
    _save_cache(cache)


def clear_rag_cache() -> None:
    """Clear all RAG cache entries."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()


def build_planner_intrinsic_context_with_cache(
    *,
    goal: str,
    history: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    rag_db: Path,
    num_ctx: int,
    max_chars: int,
    rag_top_k: int = 6,
    rag_char_budget: int = 10000,
    rerank_engine: str = "",
    rerank_url: str = "",
    rerank_model: str = "",
    rerank_timeout_seconds: float = 2.0,
    rag_embedding_batch_size: int = 4,
) -> dict[str, Any]:
    """Build intrinsic context with RAG cache optimization.
    
    First checks cache for semantically equivalent goals. If cache miss,
    performs fresh RAG query and caches the result.
    
    NOTE: This function is a placeholder for documentation purposes.
    Actual implementation should be integrated into turn.py or loop.py
    where intrinsic_context is built.
    """
    # Placeholder implementation - actual integration happens in turn.py
    # This function documents the caching strategy without creating circular imports
    return {
        "schema": "planner_intrinsic_context.v1",
        "retrieved_memory": {},
        "retrieved_rag_chunks": {
            "source": "sqlite_fts5_rag",
            "db": str(rag_db),
            "status": "placeholder",
            "count": 0,
            "items": [],
        },
        "budget_report": {
            "cached_hit": False,
            "num_ctx_effective": int(num_ctx or 0),
            "max_chars": int(max_chars or 0),
            "rag_char_budget": int(rag_char_budget or 0),
        },
    }


__all__ = [
    "get_cached_rag_result",
    "invalidate_rag_cache",
    "clear_rag_cache",
    "build_planner_intrinsic_context_with_cache",
]