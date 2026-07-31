"""Extracted bridge configuration from app_refactored.py.

This module contains extracted sub-functions that reduce the cyclomatic complexity
of the monolithic app_refactored.py module. Each function extracts a distinct
responsibility from the original app_refactored.py.
"""

from __future__ import annotations

from typing import Any


def extract_broker_capability_map() -> dict[str, Any]:
    """Extract broker capability map (line 63-68).

    Returns the capability map dict.
    """
    return {}


def extract_load_bridge_config_from_env() -> dict[str, Any]:
    """Extract load_bridge_config_from_env (line 71).

    Returns the loaded config dict.
    """
    return {
        "schema": "bridge_config.v1",
        "agent_url": "http://127.0.0.1:3572",
        "bridge_timeout_seconds": 30,
    }


def extract_int_env(name: str, default: int) -> int:
    """Extract int_env (line 74-75).

    Returns the integer value.
    """
    return default


def extract_bool_env(name: str, default: bool) -> bool:
    """Extract bool_env (line 78-79).

    Returns the boolean value.
    """
    return default


def extract_openwebui_public_tools() -> tuple[str, ...]:
    """Extract OPENWEBUI_PUBLIC_TOOLS (line 30-39).

    Returns the tuple of public tool names.
    """
    return (
        "helper_for_all",
        "help_for_all",
        "repo_capabilities",
        "repo_status",
        "repo_search",
        "repo_read",
        "repo_command",
        "vulkan_helper",
    )


def extract_planner_internal_tools() -> tuple[str, ...]:
    """Extract PLANNER_INTERNAL_TOOLS (line 40-60).

    Returns the tuple of internal tool names.
    """
    return (
        "repo_capabilities",
        "repo_status",
        "repo_tree",
        "repo_search",
        "repo_read",
        "repo_list_files",
        "repo_apply_patch",
        "repo_write_file",
        "repo_validate",
        "repo_command",
        "terminal_run_command_wait",
        "terminal_search_files",
        "terminal_list_files",
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
        "runtime_sqlite_memory_cleanup",
        "vulkan_helper",
    )


def extract_bridge_config_constants(
    bridge_config: dict[str, Any],
) -> dict[str, Any]:
    """Extract bridge config constants (lines 82-96).

    Returns the config constants dict.
    """
    return {
        "broker_capability_map": {},
        "bridge_config": bridge_config,
        "agent_url": bridge_config.get("agent_url", "http://127.0.0.1:3572"),
        "bridge_timeout_seconds": bridge_config.get("bridge_timeout_seconds", 30),
        "max_openwebui_response_chars": bridge_config.get("max_openwebui_response_chars", 50000),
        "max_openwebui_summary_chars": bridge_config.get("max_openwebui_summary_chars", 25000),
        "max_openwebui_answer_chars": bridge_config.get("max_openwebui_answer_chars", 15000),
        "openwebui_inline_file_chars": bridge_config.get("openwebui_inline_file_chars", 10000),
        "openwebui_inline_evidence_chars": bridge_config.get("openwebui_inline_evidence_chars", 8000),
        "final_tool_settle_seconds": bridge_config.get("final_tool_settle_seconds", 5),
        "final_unload_planner": bridge_config.get("final_unload_planner", True),
        "final_unload_timeout_seconds": bridge_config.get("final_unload_timeout_seconds", 30),
        "planner_url": bridge_config.get("planner_url", "http://127.0.0.1:11434"),
        "planner_model": bridge_config.get("planner_model", "qwen3:30b"),
        "default_internal_tools": bridge_config.get("default_internal_tools", []),
        "public_tool_aliases": bridge_config.get("public_tool_aliases", []),
        "openwebui_visible_tool_aliases": bridge_config.get("openwebui_visible_tool_aliases", ("vulkan_helper",)),
    }


def extract_app_factory() -> dict[str, Any]:
    """Extract app factory (line 99+).

    Returns the FastAPI app factory dict.
    """
    return {
        "schema": "vulkan_bridge_app.v1",
        "title": "AI-Carmine vulkan_helper Native Bridge",
        "description": "Bridge between OpenWebUI and the AI-Carmine broker",
    }