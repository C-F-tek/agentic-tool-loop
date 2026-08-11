"""Constants for Full0To10 repo quality packet."""
from __future__ import annotations

PACKET_JSON = "full0to10_repo_quality_packet.json"
PACKET_MD = "full0to10_repo_quality_packet.md"
INVENTORY_JSON = "full0to10_repo_quality_inventory.json"
FINDINGS_JSON = "full0to10_repo_quality_findings.json"
TOOL_PLAN_JSON = "full0to10_repo_quality_tool_plan.json"

DEFAULT_SCAN_ROOTS = (
    "README.md",
    "docs",
    "CHATGPT",
    "Tools/ai",
    "Tools/workflow",
    "Tools/validation",
)

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".ps1", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"
}

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "output", "renders", "node_modules",
    "indexAI/code_chunks", "indexAI/project_code_chunks",
}

MAX_DEFAULT_FILES = 240
MAX_PREVIEW_CHARS = 6000

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "external_tool_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
}
