"""Canonical tool registry for the 3571/3572 broker contract.

Merged from tool_schemas.py schema functions and tool_contract.py imports.
This module owns:
- ToolSchema dataclass (immutable schema builder)
- PLANNER_INTERNAL_TOOLS, OPENWEBUI_PUBLIC_TOOLS, MCP_PUBLIC_TOOLS lists
- TOOLS_SCHEMA, TOOL_ARGUMENT_CONTRACTS, VALID_INTERNAL_TOOLS exports
- tools_schema(), registry_hash(), capability_map() factory functions
- TOOL_ALIASES, WRITE_GUARDED_TOOLS, PURE_READ_TOOLS classifications

Imported by tool_contract.py for normalize_tool_name, parse_tool_call, etc.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Schema builder dataclass (§8.5 — Objects that should be dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSchema:
    """Immutable tool schema definition with optional argument contract."""

    name: str
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    requires_one_of: list[list[str]] = field(default_factory=list)
    argument_contract: dict[str, Any] = field(default_factory=dict)

    def build(self) -> dict[str, Any]:
        """Build the dict representation for the OpenWebUI/3572 contract."""
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": dict(self.properties),
        }
        if self.required:
            parameters["required"] = list(self.required)
        if self.requires_one_of:
            parameters["requires_one_of"] = [list(group) for group in self.requires_one_of]
        if self.argument_contract:
            parameters["argument_contract"] = dict(self.argument_contract)
        return {
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            }
        }


# ---------------------------------------------------------------------------
# Tool classification lists (from tool_schemas.py)
# ---------------------------------------------------------------------------

PLANNER_INTERNAL_TOOLS: list[str] = sorted([
    "repo_read", "repo_search", "repo_tree", "repo_list_files",
    "repo_patch", "repo_apply_unified_diff", "repo_write_file",
    "terminal_list_files", "terminal_search_files", "terminal_run_command_wait",
    "memory_tools_public", "scratchpad_tools_public", "terminal_tools_public",
    "vulkan_helper", "repo_command", "repo_semantic_search",
])

OPENWEBUI_PUBLIC_TOOLS: list[str] = sorted([
    "openwebui_status", "openwebui_version", "openwebui_tools",
    "openwebui_capabilities", "openwebui_diff", "openwebui_search", "openwebui_read",
])

MCP_PUBLIC_TOOLS: list[str] = sorted([
    "aicarmine_repo_state_health", "aicarmine_repo_state_status",
    "aicarmine_repo_search_rg", "aicarmine_repo_search_fd",
    "aicarmine_repo_validate_ruff", "aicarmine_repo_validate_pyright",
])

WRITE_GUARDED_TOOLS: frozenset[str] = frozenset({
    "repo_patch", "repo_apply_unified_diff", "repo_write_file",
    "terminal_run_command_wait",
})

PURE_READ_TOOLS: frozenset[str] = frozenset({
    "repo_read", "repo_search", "repo_tree", "repo_list_files",
    "terminal_list_files", "terminal_search_files",
})

READ_ONLY_TOOLS: frozenset[str] = PURE_READ_TOOLS  # Compatibility alias

STATE_MUTATING_TOOLS: frozenset[str] = WRITE_GUARDED_TOOLS - PURE_READ_TOOLS

COMMAND_EXEC_TOOLS: frozenset[str] = frozenset({"terminal_run_command_wait"})


# ---------------------------------------------------------------------------
# Tool aliases (from tool_contract.py imports)
# ---------------------------------------------------------------------------

TOOL_ALIASES: dict[str, str] = {
    "read": "repo_read",
    "search": "repo_search",
    "tree": "repo_tree",
    "list_files": "repo_list_files",
    "patch": "repo_patch",
    "apply_diff": "repo_apply_unified_diff",
    "write_file": "repo_write_file",
    "ls": "terminal_list_files",
    "grep": "terminal_search_files",
    "run": "terminal_run_command_wait",
}


# ---------------------------------------------------------------------------
# Schema definitions (from tool_schemas.py _SCHEMAS)
# ---------------------------------------------------------------------------

def _tool_schema(
    name: str,
    description: str,
    *,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    requires_one_of: list[list[str]] | None = None,
    argument_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a schema dict from component parts."""
    ts = ToolSchema(
        name=name,
        description=description,
        properties=properties or {},
        required=list(required) if required else [],
        requires_one_of=[list(g) for g in (requires_one_of or [])],
        argument_contract=dict(argument_contract) if argument_contract else {},
    )
    return ts.build()


# Lazy schema loading to avoid circular imports
def _load_schemas() -> dict[str, dict[str, Any]]:
    """Load schemas from tool_schemas.py (avoids circular import at module level)."""
    try:
        from .tool_schemas import _SCHEMAS as base_schemas
        return dict(base_schemas)
    except ImportError:
        return {}

_loaded_schemas: dict[str, dict[str, Any]] | None = None


def _get_schemas() -> dict[str, dict[str, Any]]:
    global _loaded_schemas
    if _loaded_schemas is None:
        _loaded_schemas = _load_schemas()
    return _loaded_schemas


def tools_schema() -> list[dict[str, Any]]:
    """Return deep copies of all internal tool schemas."""
    schemas = _get_schemas()
    return [copy.deepcopy(schemas[name]) for name in PLANNER_INTERNAL_TOOLS if name in schemas]


TOOLS_SCHEMA: list[dict[str, Any]] = []
TOOL_ARGUMENT_CONTRACTS: dict[str, dict[str, Any]] = {}
VALID_INTERNAL_TOOLS: frozenset[str] = frozenset(PLANNER_INTERNAL_TOOLS)
VALID_INTERNAL_TOOLS_LIST: list[str] = sorted(VALID_INTERNAL_TOOLS)
VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN: list[str] = [
    name for name in VALID_INTERNAL_TOOLS_LIST if name != "vulkan_helper"
]
VALID_INTERNAL_TOOLS_PROMPT: str = "|".join(VALID_INTERNAL_TOOLS_LIST)
VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN: str = "|".join(
    VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN
)
HELPER_PUBLIC_ALIASES: frozenset[str] = frozenset({"helper_for_all", "help_for_all", "helper", "help"})


REGISTRY_VERSION = "2026-06-01.registry-v2"
RUNTIME_CONTRACT = (
    "3571 receives OpenWebUI tool call -> 3571 forwards to 3572 and waits -> "
    "3572 runs the agentic planner loop -> 3572 wraps the terminal result -> "
    "3572 returns wrapper to 3571 -> 3571 returns ok/result wrapper to OpenWebUI"
)


def registry_hash() -> str:
    """Compute SHA-256 hash of the complete registry state."""
    payload = {
        "version": REGISTRY_VERSION,
        "planner_internal": PLANNER_INTERNAL_TOOLS,
        "openwebui_public": OPENWEBUI_PUBLIC_TOOLS,
        "mcp_public": MCP_PUBLIC_TOOLS,
        "write_guarded": sorted(WRITE_GUARDED_TOOLS),
        "pure_read": sorted(PURE_READ_TOOLS),
        "state_mutating": sorted(STATE_MUTATING_TOOLS),
        "command_exec": sorted(COMMAND_EXEC_TOOLS),
        "aliases": TOOL_ALIASES,
        "schemas": tools_schema(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capability_map() -> dict[str, Any]:
    """Return full capability surface map for the registry."""
    schemas = tools_schema()
    return {
        "registry_version": REGISTRY_VERSION,
        "registry_hash": registry_hash(),
        "runtime_contract": RUNTIME_CONTRACT,
        "surfaces": {
            "openwebui_public": list(OPENWEBUI_PUBLIC_TOOLS),
            "planner_internal": list(PLANNER_INTERNAL_TOOLS),
            "mcp_public": list(MCP_PUBLIC_TOOLS),
            "write_guarded": sorted(WRITE_GUARDED_TOOLS),
            "read_only": sorted(READ_ONLY_TOOLS),
            "pure_read": sorted(PURE_READ_TOOLS),
            "state_mutating": sorted(STATE_MUTATING_TOOLS),
            "command_exec": sorted(COMMAND_EXEC_TOOLS),
        },
        "tool_effect_notes": {
            "read_only": "Compatibility alias for pure_read; excludes state-mutating memory/RAG writes.",
            "repo_semantic_search": "Planner-internal RAG search; default reindex=true writes the RAG SQLite index.",
            "mcp_rag": "Codex MCP RAG is exposed by services/codex_bridge/rag_mcp_server.py, not by MCP_PUBLIC_TOOLS here.",
        },
        "surface_policy": {
            "3571": "OpenWebUI public surface; forwards to 3572 and waits for the wrapped terminal result.",
            "3572": "Agentic planner loop; validates, repairs structured failures, executes internal tools.",
            "memory_tools_public_on_openwebui": False,
            "scratchpad_tools_public_on_openwebui": False,
            "terminal_tools_public_on_openwebui": False,
        },
        "module": __name__,
        "schema_tools": [item["function"]["name"] for item in schemas],
    }


# Backward compatibility re-export (tool_schemas.py imports these)
# These are populated lazily when tool_schemas.py is imported
try:
    from .tool_schemas import _SCHEMAS as _BACKING_SCHEMAS
    TOOLS_SCHEMA = tools_schema()
    TOOL_ARGUMENT_CONTRACTS = {
        name: copy.deepcopy(schema.get("function", {}).get("argument_contract") or {})
        for name, schema in _BACKING_SCHEMAS.items()
    }
except ImportError:
    pass  # Lazy loading handled by tool_schemas.py itself
