#!/usr/bin/env python3
"""
AICarmine Runtime Tool Discovery Cache with keyword indexing.

Maintains a local cache of the MCP tool surface discovered at runtime.
Includes keyword-indexed lookup for immediate tool resolution without
repeated discovery calls.

Updated by aicarmine-codex-ops mcp_inventory_probe, read by pre-tool observer.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).resolve().parents[2] / "state" / "codex_bridge" / "cache"
CACHE_FILE = CACHE_DIR / "tool_surface_cache.json"
CACHE_TTL_SECONDS = 600  # 10 minutes (longer TTL reduces discovery overhead)


# ---------------------------------------------------------------------------
# Keyword indexing helpers
# ---------------------------------------------------------------------------

# Common Italian/English keywords per tool category
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "repo/read": ["leggi", "read", "content", "file", "contenuto"],
    "repo/listing": ["elenca", "list", "files", "directory", "ls"],
    "repo/search": ["cerca", "search", "grep", "find", "codice", "code"],
    "repo/state": ["stato", "status", "branch", "commit", "dirty"],
    "repo/validate": ["valida", "validate", "check", "lint", "test", "ruff", "pyright"],
    "repo/write": ["scrivi", "write", "apply", "patch", "modifica"],
    "git/history": ["log", "storia", "commits", "storico"],
    "git/diff": ["diff", "cambiamenti", "differenze"],
    "git/blame": ["blame", "chi", "scritto", "author"],
    "job/events": ["eventi", "events", "log", "esecuzione"],
    "job/final": ["risultato", "result", "finale", "output"],
    "memory/search": ["memoria", "memory", "cerca", "search"],
    "memory/write": ["scrivi", "write", "salva", "upsert"],
    "rag/query": ["semantico", "semantic", "rag", "query"],
    "search/rg": ["cerca", "search", "grep", "ripgrep"],
    "search/fd": ["trova", "find", "file", "pattern"],
    "search/ctags": ["simboli", "symbols", "ctags", "definizioni"],
    "sqlite/query": ["sqlite", "query", "database", "sql"],
    "agentic/run": ["agentic", "task", "avvia", "run", "loop"],
    "ops/snapshot": ["snapshot", "servizi", "services", "state"],
}


def _build_keyword_index(servers: dict) -> dict[str, list[str]]:
    """Build a keyword-to-tool-name index from server data."""
    index: dict[str, list[str]] = {}
    for server_name, server_data in servers.items():
        for tool in server_data.get("tools", []):
            tool_name = tool.get("name", "")
            tool_desc = tool.get("description", "").lower()
            # Index description words (4+ chars to avoid noise)
            for word in re.findall(r'[a-z]{4,}', tool_desc):
                if word not in index:
                    index[word] = []
                if tool_name not in index[word]:
                    index[word].append(tool_name)
    return index


def _load_or_build_keyword_index(cache: dict) -> dict[str, list[str]]:
    """Load keyword index from cache, or build it if missing."""
    if "keyword_index" in cache and isinstance(cache["keyword_index"], dict):
        return cache["keyword_index"]
    # Build from scratch
    index = _build_keyword_index(cache.get("servers", {}))
    cache["keyword_index"] = index
    return index


def _resolve_by_keywords(query: str, keyword_index: dict[str, list[str]]) -> list[tuple[str, int]]:
    """Resolve tool names by counting matching keywords in query."""
    query_lower = query.lower()
    query_words = set(re.findall(r'[a-z]{3,}', query_lower))

    scores: dict[str, int] = {}
    for word in query_words:
        if word in keyword_index:
            for tool_name in keyword_index[word]:
                scores[tool_name] = scores.get(tool_name, 0) + 1

    # Return sorted by score descending
    return sorted(scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# Cache operations
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_tool_surface_cache() -> dict[str, Any] | None:
    """Load the tool surface cache. Returns None if cache is missing or expired."""
    if not CACHE_FILE.exists():
        return None

    try:
        stat = CACHE_FILE.stat()
        mtime = stat.st_mtime
        now = time.time()

        if (now - mtime) > CACHE_TTL_SECONDS:
            return None  # Cache expired

        content = CACHE_FILE.read_text(encoding="utf-8")
        data = json.loads(content)

        # Validate cache structure
        if data.get("schema") != "aicarmine_tool_surface_cache.v1":
            return None

        return data

    except (json.JSONDecodeError, OSError, KeyError):
        return None


def save_tool_surface_cache(server_tools: dict[str, list[dict[str, Any]]]) -> None:
    """Save the tool surface cache with keyword index."""
    _ensure_cache_dir()

    cache = {
        "schema": "aicarmine_tool_surface_cache.v1",
        "version": "2.0.0",
        "created_at": time.time(),
        "ttl_seconds": CACHE_TTL_SECONDS,
        "servers": {},
        "keyword_index": {},  # Will be populated below
    }

    for server_name, tools in server_tools.items():
        cache["servers"][server_name] = {
            "tool_count": len(tools),
            "tools": [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                }
                for t in tools
            ],
        }

    # Build keyword index
    cache["keyword_index"] = _build_keyword_index(cache["servers"])

    CACHE_FILE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_cached_tool_by_name(tool_name: str) -> dict[str, Any] | None:
    """Get a specific tool definition from cache by name."""
    cache = load_tool_surface_cache()
    if cache is None:
        return None

    for server_name, server_data in cache.get("servers", {}).items():
        for tool in server_data.get("tools", []):
            if tool.get("name") == tool_name:
                return {
                    "tool_name": tool["name"],
                    "description": tool["description"],
                    "server_name": server_name,
                    "parameters": tool.get("parameters", {}),
                }

    return None


def resolve_tool_by_query(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Resolve tool names by keyword matching against cached descriptions.

    Uses a lightweight keyword scoring system to find the best matching tools
    for a given query string without calling MCP tools/list.

    Args:
        query: Natural language query (Italian or English)
        top_k: Number of results to return

    Returns:
        List of dicts with tool_name, server_name, score
    """
    cache = load_tool_surface_cache()
    if cache is None:
        return []

    keyword_index = _load_or_build_keyword_index(cache)
    scored = _resolve_by_keywords(query, keyword_index)

    results = []
    for tool_name, score in scored[:top_k]:
        cached = get_cached_tool_by_name(tool_name)
        if cached:
            results.append({
                **cached,
                "score": score,
            })

    return results


def get_tools_by_category(category: str) -> list[dict[str, Any]]:
    """Get all tools in a category from cache."""
    cache = load_tool_surface_cache()
    if cache is None:
        return []

    result = []
    for server_name, server_data in cache.get("servers", {}).items():
        for tool in server_data.get("tools", []):
            tool_desc = tool.get("description", "").lower()
            if category.lower() in tool_desc:
                result.append({
                    "tool_name": tool["name"],
                    "description": tool["description"],
                    "server_name": server_name,
                })

    return result


def get_category_index() -> dict[str, list[str]]:
    """Get the category-to-tools index from cache."""
    cache = load_tool_surface_cache()
    if cache is None:
        return {}

    index: dict[str, list[str]] = {}
    for server_name, server_data in cache.get("servers", {}).items():
        for tool in server_data.get("tools", []):
            desc = tool.get("description", "").lower()
            # Infer category from description keywords
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in desc for kw in keywords):
                    if cat not in index:
                        index[cat] = []
                    if tool["name"] not in index[cat]:
                        index[cat].append(tool["name"])
                    break

    return index


def is_cache_fresh() -> bool:
    """Check if the cache exists and is not expired."""
    return load_tool_surface_cache() is not None


def invalidate_cache() -> None:
    """Remove the cache file."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()