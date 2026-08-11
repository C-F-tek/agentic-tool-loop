"""Build a Full0To10 runtime tool registry manifest."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import MEMORY_TOOL_DEFAULTS, MEMORY_TOOL_NAMES, TOOL_SAFETY_FLAGS


def memory_tool_record(name: str) -> dict[str, Any]:
    write_ops = {"memory_init", "memory_add_text", "memory_add_file", "memory_embed_missing"}
    return {
        "name": name,
        "category": "sqlite_memory",
        "adapter": "Tools/ai/full0to10_runtime_tool.py",
        "default_args": MEMORY_TOOL_DEFAULTS,
        "writes_runtime_db": name in write_ops,
        "writes_source": False,
        "requires_provider": False,
        "safe_default": True,
        "safety_flags": TOOL_SAFETY_FLAGS,
    }


def build_runtime_tool_registry(repo_root: Path) -> dict[str, Any]:
    tools = [memory_tool_record(name) for name in MEMORY_TOOL_NAMES]
    return {
        "kind": "full0to10_runtime_tool_registry",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "repo_root": str(repo_root.resolve()),
        "tool_count": len(tools),
        "tools": tools,
        "broker_bridge_ready": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
    }
