"""Constants for controlled Markdown split."""
from __future__ import annotations

SUPPORTED_KIND = "markdown_split"
SHADOW_SUFFIX = ".split"
MAX_SECTIONS = 80
MAX_SLUG_CHARS = 72
MAX_CHILD_FILENAME_CHARS = 96
SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "persistent_memory_write_performed": False,
}
