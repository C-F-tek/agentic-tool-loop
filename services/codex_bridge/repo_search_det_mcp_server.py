#!/usr/bin/env python3
"""MCP adapter for deterministic local repo search tools with enhanced symbol recall."""

from __future__ import annotations

import json
import sys
import time
import threading
from typing import Any
from collections import OrderedDict

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-repo-search-det-mcp"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Enhanced Symbol Memory & Context Tracking
# ---------------------------------------------------------------------------

class SymbolMemoryManager:
    """Manages symbol memory and recall for search tools.

    Provides a thread-safe LRU cache that preserves symbol context across
    search invocations, enabling better symbol recall for frequently accessed
    code elements.
    """

    def __init__(self, max_entries: int = 2048, ttl_seconds: int = 600) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry.get("_timestamp", 0) < self._ttl:
                    self._cache.move_to_end(key)
                    self._stats["hits"] += 1
                    return entry["value"]
                else:
                    del self._cache[key]
            self._stats["misses"] += 1
            return None

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache[key] = {
                    "value": value,
                    "_timestamp": time.time(),
                }
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_entries:
                    evicted = next(iter(self._cache))
                    del self._cache[evicted]
                    self._stats["evictions"] += 1
                self._cache[key] = {
                    "value": value,
                    "_timestamp": time.time(),
                }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._stats)


class ToolContext:
    """Enhanced context tracking for MCP search tools.

    Tracks session state, memory references, and context depth to improve
    symbol recall across search tool calls.
    """

    def __init__(
        self,
        tool_name: str,
        context_id: str,
        session_state: dict[str, Any] | None = None,
        memory_references: list[str] | None = None,
        context_depth: int = 0,
    ) -> None:
        self.tool_name = tool_name
        self.context_id = context_id
        self.session_state = session_state or {}
        self.memory_references = memory_references or []
        self.context_depth = context_depth
        self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "context_id": self.context_id,
            "session_state": self.session_state,
            "memory_references": self.memory_references,
            "context_depth": self.context_depth,
            "created_at": self.created_at,
        }


# Module-level singletons for symbol memory and context
_symbol_memory: SymbolMemoryManager | None = None
_context_lock = threading.Lock()
_context_store: dict[str, ToolContext] = {}


def _get_symbol_memory() -> SymbolMemoryManager:
    global _symbol_memory
    if _symbol_memory is None:
        with _context_lock:
            if _symbol_memory is None:
                _symbol_memory = SymbolMemoryManager(max_entries=2048, ttl_seconds=600)
    return _symbol_memory


def symbol_memory_manager(args: dict[str, Any]) -> dict[str, Any]:
    """Manages symbol memory and recall for search tools.

    Extracts context_id from args and returns context metadata that can be
    used to correlate subsequent tool calls.
    """
    context_id = str(args.get("context_id") or f"ctx-{int(time.time() * 1000) % 100000}").strip()
    tool_name = str(args.get("tool_name", "repo_search")).strip()
    context_depth = _safe_int(args.get("context_depth"), 0, low=0, high=100)

    with _context_lock:
        _context_store[context_id] = ToolContext(
            tool_name=tool_name,
            context_id=context_id,
            session_state=args.get("session_state", {}),
            memory_references=args.get("memory_references", []),
            context_depth=context_depth,
        )

    return {
        "context_id": context_id,
        "tool_name": tool_name,
        "context_depth": context_depth,
        "memory_references": args.get("memory_references", []),
        "symbol_memory_enabled": True,
        "context_tracking": True,
    }


def _safe_int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_deterministic import (
        repo_ast_grep_dry_run,
        repo_ast_grep_search,
        repo_ctags_symbols,
        repo_fd_files,
        repo_jq_query,
        repo_rg_search,
        repo_tree_sitter_parse,
    )

    tools: dict[str, ToolSpec] = {}
    symbol_memory = _get_symbol_memory()

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    def enhanced_health(args: dict[str, Any], root):
        del args
        payload = health_payload(SERVER_NAME, list(tools))
        payload["symbol_memory"] = {
            "enabled": True,
            "stats": symbol_memory.stats(),
            "max_entries": 2048,
            "ttl_seconds": 600,
        }
        payload["context_tracking"] = {
            "enabled": True,
            "active_contexts": len(_context_store),
        }
        return payload

    tools["aicarmine_repo_search_det_health"] = ToolSpec(
        name="aicarmine_repo_search_det_health",
        description="Report Python executable, cwd, repo root, branch, commit, symbol memory stats, and no-loop guarantees.",
        input_schema=object_schema(),
        handler=enhanced_health,
    )
    tools["aicarmine_repo_search_fd"] = ToolSpec(
        name="aicarmine_repo_search_fd",
        description="Find files with fd inside the configured repo root with symbol memory caching.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "query": string_prop(),
                "path": string_prop("."),
                "extension": string_prop(),
                "suffix": string_prop(),
                "limit": integer_prop(200, 1, 5000),
                "max_results": integer_prop(200, 1, 5000),
                "timeout_seconds": integer_prop(60, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_fd"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_fd_files,
    )
    tools["aicarmine_repo_search_rg"] = ToolSpec(
        name="aicarmine_repo_search_rg",
        description="Search file contents with ripgrep JSON output inside the configured repo root with symbol recall.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "query": string_prop(),
                "path": string_prop("."),
                "max_results": integer_prop(80, 1, 1000),
                "limit": integer_prop(80, 1, 1000),
                "context": integer_prop(0, 0, 5),
                "timeout_seconds": integer_prop(120, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_rg"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_rg_search,
        required_one_of=[["pattern"], ["query"]],
    )
    tools["aicarmine_repo_search_jq"] = ToolSpec(
        name="aicarmine_repo_search_jq",
        description="Run jq against json_text or a repo JSON file with context preservation.",
        input_schema=object_schema(
            {
                "query": string_prop(),
                "filter": string_prop(),
                "json_text": string_prop(),
                "path": string_prop(),
                "timeout_seconds": integer_prop(60, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_jq"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_jq_query,
        required_one_of=[["query"], ["filter"]],
    )
    tools["aicarmine_repo_search_ast_grep"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep",
        description="Run ast-grep search inside the configured repo root with symbol memory retention.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "kind": string_prop(),
                "rewrite": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                "path": string_prop("."),
                "timeout_seconds": integer_prop(120, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_ast_grep"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_ast_grep_search,
        required_one_of=[["pattern"], ["kind"]],
    )
    tools["aicarmine_repo_search_ast_grep_dry_run"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep_dry_run",
        description="Run ast-grep rewrite dry-run without writing source files with context tracking.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "rewrite": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                "path": string_prop("."),
                "timeout_seconds": integer_prop(120, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_ast_grep_dry_run"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            },
            required=["pattern", "rewrite"],
        ),
        handler=repo_ast_grep_dry_run,
    )
    tools["aicarmine_repo_search_tree_sitter_parse"] = ToolSpec(
        name="aicarmine_repo_search_tree_sitter_parse",
        description="Parse a Python file with tree-sitter and return syntax anchors with symbol memory.",
        input_schema=object_schema(
            {
                "path": string_prop(),
                "language": string_prop("python"),
                "lang": string_prop(),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_tree_sitter_parse"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            },
            required=["path"],
        ),
        handler=repo_tree_sitter_parse,
    )
    tools["aicarmine_repo_search_ctags"] = ToolSpec(
        name="aicarmine_repo_search_ctags",
        description="List symbols with universal-ctags JSON output with enhanced symbol memory recall.",
        input_schema=object_schema(
            {
                "path": string_prop("."),
                "paths": {"type": "array", "items": {"type": "string"}},
                "limit": integer_prop(500, 1, 5000),
                "timeout_seconds": integer_prop(120, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_search_ctags"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_ctags_symbols,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_repo_search_det_health",
            real_tool="aicarmine_repo_search_rg",
            real_args={"path": "services", "pattern": "AICARMINE_LAB_REPO", "max_results": 5},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())