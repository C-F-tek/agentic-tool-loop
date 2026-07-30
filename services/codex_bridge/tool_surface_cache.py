#!/usr/bin/env python3
"""
AICarmine Runtime Tool Discovery Cache.

Maintains a local cache of the MCP tool surface discovered at runtime.
Updated by aicarmine-codex-ops mcp_inventory_probe, read by pre-tool observer.

This enables immediate tool resolution without repeated discovery calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).resolve().parents[2] / "state" / "codex_bridge" / "cache"
CACHE_FILE = CACHE_DIR / "tool_surface_cache.json"
CACHE_TTL_SECONDS = 300  # 5 minutes


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
    """Save the tool surface cache."""
    _ensure_cache_dir()

    cache = {
        "schema": "aicarmine_tool_surface_cache.v1",
        "version": "1.0.0",
        "created_at": time.time(),
        "ttl_seconds": CACHE_TTL_SECONDS,
        "servers": {},
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
                    "parameters": tool["parameters"],
                }

    return None


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


def is_cache_fresh() -> bool:
    """Check if the cache exists and is not expired."""
    return load_tool_surface_cache() is not None


def invalidate_cache() -> None:
    """Remove the cache file."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()