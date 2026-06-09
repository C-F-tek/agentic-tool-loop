"""Canonical tool registry for the 3571/3572 broker contract.

This module is deliberately pure data plus small pure helpers. It does not
dispatch tools, read request payloads, call HTTP, or touch job state.

All schema data and tool lists are imported from tool_schemas; this file
provides the same public API for existing consumers.
"""
from __future__ import annotations

from typing import Any

from .tool_schemas import (
    HELPER_PUBLIC_ALIASES,
    MCP_PUBLIC_TOOLS,
    OPENWEBUI_PUBLIC_TOOLS,
    PLANNER_INTERNAL_TOOLS,
    READ_ONLY_TOOLS,
    TOOL_ALIASES,
    TOOL_ARGUMENT_CONTRACTS,
    TOOLS_SCHEMA,
    VALID_INTERNAL_TOOLS,
    VALID_INTERNAL_TOOLS_LIST,
    VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN,
    VALID_INTERNAL_TOOLS_PROMPT,
    VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN,
    WRITE_GUARDED_TOOLS,
    REGISTRY_VERSION as _registry_version,
    RUNTIME_CONTRACT as _runtime_contract,
)

REGISTRY_VERSION = _registry_version
RUNTIME_CONTRACT = _runtime_contract


def tools_schema() -> list[dict[str, Any]]:
    return TOOLS_SCHEMA


def registry_hash() -> str:
    from .tool_schemas import registry_hash as _rh
    return _rh()


def capability_map() -> dict[str, Any]:
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
        },
        "surface_policy": {
            "3571": "OpenWebUI public surface; forwards to 3572 and waits for the wrapped terminal result.",
            "3572": "Agentic planner loop; validates, repairs structured failures, executes internal tools.",
            "memory_tools_public_on_openwebui": False,
            "scratchpad_tools_public_on_openwebui": False,
            "terminal_tools_public_on_openwebui": False,
        },
        "module": __name__,
        "schema_tools": [item["function"]["name"] for item in TOOLS_SCHEMA],
    }
