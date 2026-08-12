"""Runtime tool constants for Full0To10."""
from __future__ import annotations

MEMORY_TOOL_NAMES = (
    "memory_init",
    "memory_add_text",
    "memory_add_file",
    "memory_search",
    "memory_embed_missing",
    "memory_manifest",
)

MEMORY_TOOL_DEFAULTS = {
    "db": "output/ai_runtime_memory/operational_context.sqlite",
    "namespace": "default",
    "embedding_provider": "none",
    "embedding_model": "hash-local-v1",
    "ollama_url": "http://127.0.0.1:11434",
}

TOOL_SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
