"""Constants for Full0To10 auto-refactor planner."""
from __future__ import annotations

DEFAULT_SCAN_ROOTS = ("Tools", "Scripting", "docs", "CHATGPT")
CODE_SUFFIXES = (".py", ".ps1")
MD_SUFFIXES = (".md",)
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "output",
    "renders",
    "indexAI",
}
CODE_SPLIT_LINE_THRESHOLD = 300
MD_SPLIT_LINE_THRESHOLD = 500
MAX_PATCH_SPECS = 200
HARDWARE_KEYWORDS = (
    "gpu",
    "npu",
    "openvino",
    "ollama",
    "cuda",
    "gpu.0",
    "parallel_gpu",
    "device",
)
