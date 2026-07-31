"""Configuration loading and environment variable handling extracted from app.py."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def load_bridge_config() -> dict[str, Any]:
    """Load bridge configuration from environment variables."""
    from .config import BridgeConfig, int_env, bool_env, load_bridge_config_from_env
    
    config = load_bridge_config_from_env()
    return {
        "agent_url": config.agent_url,
        "bridge_timeout_seconds": config.bridge_timeout_seconds,
        "max_openwebui_response_chars": config.max_openwebui_response_chars,
        "max_openwebui_summary_chars": config.max_openwebui_summary_chars,
        "max_openwebui_answer_chars": config.max_openwebui_answer_chars,
        "openwebui_inline_file_chars": config.openwebui_inline_file_chars,
        "openwebui_inline_evidence_chars": config.openwebui_inline_evidence_chars,
        "final_tool_settle_seconds": config.final_tool_settle_seconds,
        "final_unload_planner": config.final_unload_planner,
        "final_unload_timeout_seconds": config.final_unload_timeout_seconds,
    }


def int_env(name: str, default: int) -> int:
    """Read an integer environment variable with fallback."""
    try:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return int(raw)
    except (ValueError, TypeError):
        return default


def bool_env(name: str, default: bool) -> bool:
    """Read a boolean environment variable with fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def resolve_cache_dir() -> Path:
    """Resolve the OpenWebUI tool payload cache directory."""
    env_dir = os.environ.get("AICARMINE_OPENWEBUI_TOOL_PAYLOAD_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "state" / "openwebui_tool_payloads"


def resolve_config_values() -> dict[str, Any]:
    """Resolve all configuration-dependent values for app.py."""
    config = load_bridge_config()
    
    return {
        "AGENT_URL": config["agent_url"],
        "BRIDGE_TIMEOUT_SECONDS": config["bridge_timeout_seconds"],
        "BRIDGE_MAX_OPENWEBUI_RESPONSE_CHARS": config["max_openwebui_response_chars"],
        "BRIDGE_MAX_OPENWEBUI_SUMMARY_CHARS": config["max_openwebui_summary_chars"],
        "BRIDGE_MAX_OPENWEBUI_ANSWER_CHARS": config["max_openwebui_answer_chars"],
        "BRIDGE_OPENWEBUI_INLINE_FILE_CHARS": config["openwebui_inline_file_chars"],
        "BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS": config["openwebui_inline_evidence_chars"],
        "OPENWEBUI_TOOL_PAYLOAD_CACHE_DIR": resolve_cache_dir(),
        "OPENWEBUI_FINAL_TOOL_SETTLE_SECONDS": config["final_tool_settle_seconds"],
        "OPENWEBUI_FINAL_UNLOAD_PLANNER": config["final_unload_planner"],
        "OPENWEBUI_FINAL_UNLOAD_TIMEOUT_SECONDS": config["final_unload_timeout_seconds"],
        "PLANNER_URL": config["agent_url"],  # Default to agent_url
        "PLANNER_MODEL": os.environ.get("AICARMINE_PLANNER_MODEL", ""),
        "OPENWEBUI_RETURN_MODEL": os.environ.get("AICARMINE_OPENWEBUI_RETURN_MODEL", ""),
    }