#!/usr/bin/env python3
"""MCP adapter for deterministic repo validation tools with enhanced symbol memory."""

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
    string_prop,
    integer_prop,
    safe_int,
)
from repo_probe_profiles import (
    PROFILE_ORIENTATION_SELECTOR,
    PROFILE_ORIENTATION_SHADOW_HELPERS,
    PROFILE_ORIENTATION_SHADOW_EVALUATOR,
    repo_probe_profiles,
    repo_probe_run,
)

SERVER_NAME = "aicarmine-repo-validate-mcp"
SERVER_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# Enhanced Context Handling & Symbol Memory
# ---------------------------------------------------------------------------

class SymbolMemoryManager:
    """Manages symbol memory and recall for validation tools.

    Provides a thread-safe LRU cache that preserves symbol context across
    tool invocations, reducing the need to re-analyze unchanged code.
    """

    def __init__(self, max_entries: int = 256, ttl_seconds: int = 300) -> None:
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
    """Enhanced context tracking for MCP tools.

    Tracks session state, memory references, and context depth to improve
    symbol recall across validation tool calls.
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


# Module-level singleton for symbol memory
_symbol_memory: SymbolMemoryManager | None = None
_context_lock = threading.Lock()
_context_store: dict[str, ToolContext] = {}


def _get_symbol_memory() -> SymbolMemoryManager:
    global _symbol_memory
    if _symbol_memory is None:
        with _context_lock:
            if _symbol_memory is None:
                _symbol_memory = SymbolMemoryManager(max_entries=256, ttl_seconds=300)
    return _symbol_memory


def enhanced_context_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Provides enhanced context handling for validation tools.

    Extracts context_id from args and returns context metadata that can be
    used to correlate subsequent tool calls.
    """
    context_id = str(args.get("context_id") or f"ctx-{int(time.time() * 1000) % 100000}").strip()
    tool_name = str(args.get("tool_name", "repo_validate")).strip()
    context_depth = safe_int(args.get("context_depth"), 0, low=0, high=100)

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




def paths_schema(*, default_path: str | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "path": string_prop(default_path),
        "paths": {"type": "array", "items": {"type": "string"}},
    }
    return properties


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_deterministic import (
        repo_pyright_check,
        repo_pytest_run,
        repo_ruff_check,
        repo_semgrep_scan,
        repo_shellcheck,
    )
    from aicarmine_broker.tools.repo_validate import repo_validate

    tools: dict[str, ToolSpec] = {}
    symbol_memory = _get_symbol_memory()

    def health(args: dict[str, Any], root):
        del args
        payload = health_payload(SERVER_NAME, list(tools))
        payload["probe_profiles_available"] = True
        payload["arbitrary_python_probe_allowed"] = False
        payload["probe_source_writes_performed"] = False
        payload["symbol_memory"] = {
            "enabled": True,
            "stats": symbol_memory.stats(),
            "max_entries": 256,
            "ttl_seconds": 300,
        }
        payload["context_tracking"] = {
            "enabled": True,
            "active_contexts": len(_context_store),
        }
        return payload

    tools["aicarmine_repo_validate_health"] = ToolSpec(
        name="aicarmine_repo_validate_health",
        description=(
            "Report Python executable, cwd, repo root, branch, commit, "
            "available tools, symbol memory stats, and no-loop guarantees."
        ),
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_validate_diffcheck"] = ToolSpec(
        name="aicarmine_repo_validate_diffcheck",
        description="Run repo_validate default git diff --check validation with enhanced context retention.",
        input_schema=object_schema(
            {
                "commands": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": integer_prop(300, 1, 1800),
                "continue_on_failure": {
                    "type": "boolean",
                    "default": False,
                },
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_diffcheck"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_validate,
    )
    tools["aicarmine_repo_validate_ruff"] = ToolSpec(
        name="aicarmine_repo_validate_ruff",
        description="Run ruff check with JSON diagnostics and symbol memory caching.",
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(180, 1, 1200),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_ruff"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_ruff_check,
    )
    tools["aicarmine_repo_validate_pyright"] = ToolSpec(
        name="aicarmine_repo_validate_pyright",
        description="Run pyright with JSON diagnostics and symbol memory caching.",
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(240, 1, 1200),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_pyright"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_pyright_check,
    )
    tools["aicarmine_repo_validate_pytest"] = ToolSpec(
        name="aicarmine_repo_validate_pytest",
        description=(
            "Run pytest on selected paths only when explicitly requested "
            "by the user. Includes symbol memory for test result caching."
        ),
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "marker": string_prop(),
                "maxfail": integer_prop(1, 1, 20),
                "timeout_seconds": integer_prop(300, 1, 1800),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_pytest"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_pytest_run,
    )
    tools["aicarmine_repo_validate_shellcheck"] = ToolSpec(
        name="aicarmine_repo_validate_shellcheck",
        description="Run shellcheck JSON diagnostics on selected files with context retention.",
        input_schema=object_schema(
            {
                **paths_schema(),
                "timeout_seconds": integer_prop(120, 1, 600),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_shellcheck"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_shellcheck,
        required_one_of=[["path"], ["paths"]],
    )
    tools["aicarmine_repo_validate_semgrep"] = ToolSpec(
        name="aicarmine_repo_validate_semgrep",
        description=(
            "Run semgrep JSON diagnostics with a pattern or config. "
            "Includes symbol memory for pattern reuse across calls."
        ),
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "config": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(240, 1, 1200),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_semgrep"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_semgrep_scan,
        required_one_of=[["pattern"], ["config"]],
    )
    tools["aicarmine_repo_validate_probe_profiles"] = ToolSpec(
        name="aicarmine_repo_validate_probe_profiles",
        description=(
            "List static read-only probe profiles and report optional "
            "Hypothesis availability. Does not execute arbitrary Python."
        ),
        input_schema=object_schema(),
        handler=repo_probe_profiles,
    )
    tools["aicarmine_repo_validate_probe_run"] = ToolSpec(
        name="aicarmine_repo_validate_probe_run",
        description=(
            "Run a reviewed read-only probe profile with deterministic "
            "cases, Hypothesis-generated cases, or both. No network calls "
            "or source writes are permitted by the profile."
        ),
        input_schema=object_schema(
            {
                "profile_id": {
                    "type": "string",
                    "default": PROFILE_ORIENTATION_SELECTOR,
                    "enum": [PROFILE_ORIENTATION_SELECTOR, PROFILE_ORIENTATION_SHADOW_HELPERS, PROFILE_ORIENTATION_SHADOW_EVALUATOR],
                },
                "engine": {
                    "type": "string",
                    "default": "deterministic",
                    "enum": ["deterministic", "hypothesis", "both"],
                },
                "max_examples": integer_prop(200, 1, 1000),
                "seed": integer_prop(42, 0, 2_147_483_647),
                "context_id": string_prop(),
                "tool_name": string_prop("repo_validate_probe_run"),
                "context_depth": integer_prop(0, 0, 100),
                "session_state": {"type": "object"},
                "memory_references": {"type": "array", "items": {"type": "string"}},
            }
        ),
        handler=repo_probe_run,
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
            health_tool="aicarmine_repo_validate_health",
            real_tool="aicarmine_repo_validate_diffcheck",
            real_args={
                "continue_on_failure": True,
                "timeout_seconds": 60,
            },
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())