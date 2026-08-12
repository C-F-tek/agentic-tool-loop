"""Constants for Full0To10 memory visibility assertion."""
from __future__ import annotations

REPORT_JSON = "full0to10_memory_visibility_assertion.json"
REPORT_MD = "full0to10_memory_visibility_assertion.md"

MEMORY_PATHS = (
    {
        "name": "operational_context",
        "path": "output/ai_runtime_memory/operational_context.sqlite",
        "role": "runtime_operational_context",
    },
    {
        "name": "agent_memory",
        "path": "indexAI/agent_memory/agent_memory.sqlite",
        "role": "persistent_agent_memory",
    },
)
